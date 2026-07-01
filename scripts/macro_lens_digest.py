#!/usr/bin/env python3
import argparse
import html
import json
import re
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse


DEFAULT_USER_AGENT = "stock-trading-coach-agent/1.0"


class PageParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.title = ""
        self._in_title = False
        self._skip_depth = 0
        self.text_parts = []
        self.links = []
        self._current_href = None
        self._current_text = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attr = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag == "a":
            href = attr.get("href")
            if href:
                self._current_href = urljoin(self.base_url, href)
                self._current_text = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "a" and self._current_href:
            self.links.append({
                "url": self._current_href,
                "text": " ".join(" ".join(self._current_text).split())[:180],
            })
            self._current_href = None
            self._current_text = []

    def handle_data(self, data):
        text = " ".join(str(data or "").split())
        if not text:
            return
        if self._in_title:
            self.title += text
        elif not self._skip_depth:
            self.text_parts.append(text)
            if self._current_href:
                self._current_text.append(text)


def fetch_page(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(2 * 1024 * 1024)
        charset = resp.headers.get_content_charset() or "utf-8"
    body = raw.decode(charset, errors="replace")
    parser = PageParser(url)
    parser.feed(body)
    return {
        "url": url,
        "title": html.unescape(parser.title.strip()),
        "text": html.unescape(" ".join(parser.text_parts)),
        "links": parser.links,
    }


def split_sentences(text):
    chunks = re.split(r"[。！？!?；;\n]+", text)
    return [chunk.strip() for chunk in chunks if len(chunk.strip()) >= 8]


def is_probably_block_page(text):
    sample = str(text or "")[:1000]
    if "_waf_" in sample.lower() or "captcha" in sample.lower():
        return True
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", sample))
    ascii_noise = len(re.findall(r"[A-Za-z0-9+/=]{24,}", sample))
    return chinese_chars < 12 and ascii_noise >= 2


def valid_content_sentence(sentence):
    if is_probably_block_page(sentence):
        return False
    return len(re.findall(r"[\u4e00-\u9fff]", sentence)) >= 6


def compact(text, limit=160):
    return " ".join(str(text or "").split())[:limit]


def score_macro_sentence(sentence):
    keywords = [
        "宏观", "政策", "周期", "利率", "流动性", "产业", "发展", "长期主义", "瓶颈",
        "估值", "风险偏好", "风格", "成长", "价值", "白马", "科技", "医药", "消费",
        "市场", "指数", "趋势", "经济", "全球", "中国", "美元", "人民币", "财政",
    ]
    risk_words = ["风险", "危机", "瓶颈", "衰退", "泡沫", "拥挤", "回撤", "腰斩", "不确定"]
    return sum(word in sentence for word in keywords) * 2 + sum(word in sentence for word in risk_words)


def lens_type(sentence):
    if any(word in sentence for word in ["政策", "财政", "监管", "改革"]):
        return "政策周期"
    if any(word in sentence for word in ["产业", "科技", "医药", "消费", "发展", "瓶颈"]):
        return "产业趋势"
    if any(word in sentence for word in ["风险偏好", "风格", "成长", "价值", "白马"]):
        return "市场风格"
    if any(word in sentence for word in ["长期主义", "企业", "价值", "腰斩"]):
        return "长期主义"
    if any(word in sentence for word in ["风险", "危机", "泡沫", "不确定"]):
        return "风险信号"
    return "宏观观察"


def risk_tags(sentence):
    tags = []
    if any(word in sentence for word in ["长期主义", "拿住", "未来", "价值"]):
        tags.append("可能强化持仓偏见")
    if any(word in sentence for word in ["踏空", "主线", "加速", "抢"]):
        tags.append("可能诱发追涨")
    if not any(word in sentence for word in ["数据", "公告", "财报", "政策", "利率", "订单", "营收", "利润"]):
        tags.append("可验证事实不足")
    if any(word in sentence for word in ["危机", "新生", "变局", "相信", "认知"]):
        tags.append("叙事强于交易规则")
    return tags or ["未见明显叙事风险"]


def article_from_text(url, title, text, date="无法判断"):
    if is_probably_block_page(text):
        return None
    sentences = split_sentences(text)
    sentences = [item for item in sentences if valid_content_sentence(item)]
    ranked = sorted(sentences, key=score_macro_sentence, reverse=True)
    selected = [compact(item, 180) for item in ranked[:6] if score_macro_sentence(item) > 0]
    if not selected:
        selected = [compact(item, 180) for item in sentences[:3]] or ["无法判断"]
    lenses = []
    for sentence in selected[:5]:
        lenses.append({
            "lens": lens_type(sentence),
            "observation": sentence,
            "risk_tags": risk_tags(sentence),
        })
    return {
        "title": title or "无法判断",
        "url": url,
        "date": date,
        "summary": selected[:5],
        "macro_lenses": lenses,
    }


def extract_xueqiu_user_id(url):
    parsed = urlparse(url)
    match = re.search(r"/(?:u/)?(\d{6,})", parsed.path)
    return match.group(1) if match else ""


def candidate_article_links(profile_page, user_id, limit):
    candidates = []
    seen = set()
    for link in profile_page.get("links", []):
        url = link.get("url", "")
        path = urlparse(url).path
        if user_id and user_id not in path:
            continue
        if not re.search(r"/\d{6,}/\d{6,}", path):
            continue
        if url in seen:
            continue
        seen.add(url)
        candidates.append({"url": url, "title": link.get("text", "")})
        if len(candidates) >= limit:
            break
    return candidates


def build_from_xueqiu_profile(user_url, limit, timeout):
    user_id = extract_xueqiu_user_id(user_url)
    urls = [user_url]
    if user_id:
        urls.append(f"https://xueqiu.com/{user_id}")
    profile_pages = []
    errors = []
    for url in dict.fromkeys(urls):
        try:
            profile_pages.append(fetch_page(url, timeout=timeout))
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}")

    links = []
    for page in profile_pages:
        links.extend(candidate_article_links(page, user_id, limit))
    deduped = []
    seen = set()
    for item in links:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        deduped.append(item)
        if len(deduped) >= limit:
            break

    articles = []
    article_errors = []
    for item in deduped:
        try:
            page = fetch_page(item["url"], timeout=timeout)
            title = item.get("title") or page.get("title")
            article = article_from_text(item["url"], title, page.get("text", ""))
            if article:
                articles.append(article)
            else:
                article_errors.append({"url": item["url"], "error": "blocked_or_unreadable"})
        except Exception as exc:
            article_errors.append({"url": item["url"], "error": type(exc).__name__})

    if not articles and profile_pages:
        page = profile_pages[0]
        article = article_from_text(page["url"], page.get("title") or "雪球主页可见文本", page.get("text", ""))
        if article:
            articles.append(article)
        else:
            metadata_note = "雪球返回的公开页面不是可读文章内容，可能需要登录态浏览器或手动提供具体文章。"
            article_errors.append({"url": page["url"], "error": "blocked_or_unreadable", "note": metadata_note})

    return articles, {
        "profile_fetch_errors": errors,
        "article_fetch_errors": article_errors,
        "candidate_links": len(deduped),
        "note": "若雪球页面需要登录或反爬，脚本只保存可公开抓取文本；可改用 --article-url 或 --text-file 手动补充。",
    }


def aggregate_lenses(articles):
    bucket = {}
    for article in articles:
        for lens in article.get("macro_lenses", []):
            key = (lens.get("lens"), lens.get("observation", "")[:48])
            item = bucket.setdefault(key, {
                "lens": lens.get("lens", "宏观观察"),
                "observation": lens.get("observation", "无法判断"),
                "evidence_count": 0,
                "source_urls": [],
                "risk_tags": set(),
            })
            item["evidence_count"] += 1
            if article.get("url"):
                item["source_urls"].append(article["url"])
            item["risk_tags"].update(lens.get("risk_tags", []))
    rows = []
    for item in bucket.values():
        rows.append({
            "lens": item["lens"],
            "observation": item["observation"],
            "evidence_count": item["evidence_count"],
            "source_urls": list(dict.fromkeys(item["source_urls"]))[:5],
            "risk_tags": sorted(item["risk_tags"]),
        })
    return sorted(rows, key=lambda row: (-row["evidence_count"], row["lens"], row["observation"]))[:40]


def build_digest(args):
    articles = []
    metadata = {}
    if args.source == "xueqiu":
        articles, metadata = build_from_xueqiu_profile(args.user_url, args.limit, args.timeout)
    for url in args.article_url:
        try:
            page = fetch_page(url, timeout=args.timeout)
            articles.append(article_from_text(url, page.get("title"), page.get("text", "")))
        except Exception as exc:
            metadata.setdefault("article_fetch_errors", []).append({"url": url, "error": type(exc).__name__})
    for text_file in args.text_file:
        path = Path(text_file)
        article = article_from_text("", path.stem, path.read_text(encoding="utf-8"))
        if article:
            articles.append(article)
    articles = articles[:args.limit]
    return {
        "source": {
            "name": args.source_name,
            "url": args.user_url,
            "source_type": args.source,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "limit": args.limit,
        },
        "macro_lenses": aggregate_lenses(articles),
        "articles": articles,
        "metadata": metadata,
        "storage_policy": "不保存文章全文，只保存标题、URL、摘要、宏观镜片和风险标签。",
        "usage_boundary": "宏观镜片只用于市场环境观察和教练提问，不触发个股买卖建议，不预测涨跌。",
    }


def write_index(path, digest):
    rows = []
    for article in digest.get("articles", []):
        rows.append({
            "title": article.get("title", "无法判断"),
            "url": article.get("url", ""),
            "date": article.get("date", "无法判断"),
            "lens_count": len(article.get("macro_lenses", [])),
        })
    Path(path).write_text(json.dumps({
        "updated_at": digest["source"]["updated_at"],
        "source": digest["source"],
        "articles": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="手动蒸馏宏观判断镜片，不保存文章全文")
    parser.add_argument("--source", choices=["xueqiu"], default="xueqiu")
    parser.add_argument("--source-name", default="冰冰小美")
    parser.add_argument("--user-url", default="https://xueqiu.com/u/7143769715")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--timeout", type=int, default=12)
    parser.add_argument("--article-url", action="append", default=[])
    parser.add_argument("--text-file", action="append", default=[])
    parser.add_argument("-o", "--output", default="local_state/macro_lenses.json")
    parser.add_argument("--index-output", default="local_state/source_articles_index.json")
    args = parser.parse_args()

    digest = build_digest(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_index(args.index_output, digest)
    print(f"wrote {args.output}")
    print(f"wrote {args.index_output}")
    print(f"articles={len(digest.get('articles', []))} lenses={len(digest.get('macro_lenses', []))}")


if __name__ == "__main__":
    main()
