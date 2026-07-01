#!/usr/bin/env python3
import argparse
import html
import json
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self._in_title = False
        self._skip = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style", "noscript"}:
            self._skip = True

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript"}:
            self._skip = False

    def handle_data(self, data):
        text = " ".join(str(data or "").split())
        if not text:
            return
        if self._in_title:
            self.title += text
        elif not self._skip:
            self.parts.append(text)


def load_json(path):
    if not path or not Path(path).exists():
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def fetch_url(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "stock-trading-coach-agent/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(1024 * 1024)
        content_type = resp.headers.get_content_charset() or "utf-8"
    html_text = raw.decode(content_type, errors="replace")
    parser = TextExtractor()
    parser.feed(html_text)
    return parser.title.strip(), " ".join(parser.parts)


def read_article(args):
    title = args.title
    source_url = args.url
    if args.url:
        try:
            fetched_title, text = fetch_url(args.url)
            return title or fetched_title, source_url, text
        except Exception as exc:
            return title, source_url, f"无法抓取文章：{type(exc).__name__}"
    if args.text_file:
        return title, source_url, Path(args.text_file).read_text(encoding="utf-8")
    return title, source_url, args.text or ""


def split_sentences(text):
    chunks = re.split(r"[。！？!?；;\n]+", text)
    return [chunk.strip() for chunk in chunks if len(chunk.strip()) >= 8]


def pick_viewpoints(text, limit=5):
    keywords = ["因为", "所以", "认为", "观点", "逻辑", "催化", "风险", "估值", "业绩", "资金", "情绪", "趋势"]
    sentences = split_sentences(text)
    ranked = sorted(sentences, key=lambda s: sum(token in s for token in keywords), reverse=True)
    return [html.unescape(s[:160]) for s in ranked[:limit]] or ["无法判断"]


def has_any(text, words):
    return any(word in text for word in words)


def narrative_checks(text, journal):
    combined = f"{text}\n{json.dumps(journal, ensure_ascii=False)}"
    checks = {
        "reinforces_position_bias": has_any(combined, ["坚定持有", "不用怕", "迟早", "低估", "错杀", "拿住", "信仰"]),
        "induces_chasing": has_any(combined, ["突破", "加速", "主升", "涨停", "抢筹", "踏空", "追"]),
        "has_verifiable_facts": has_any(combined, ["公告", "财报", "营收", "利润", "订单", "数据", "同比", "环比", "监管", "合同"]),
        "is_emotional_comfort": has_any(combined, ["别慌", "不用担心", "相信", "格局", "耐心", "洗盘", "情绪"]),
        "affected_today_trade": bool(journal.get("article_influenced")) or has_any(combined, ["看了文章", "受文章影响", "观点影响", "因此买", "因此卖", "因此加仓"]),
    }
    return {
        key: {
            "flag": bool(value),
            "reason": reason_for_check(key, bool(value)),
        }
        for key, value in checks.items()
    }


def reason_for_check(key, flag):
    reasons = {
        "reinforces_position_bias": "文章或 journal 可能强化已有持仓叙事。" if flag else "未发现明显强化持仓偏见的词句。",
        "induces_chasing": "文章或 journal 可能诱发追涨冲动。" if flag else "未发现明显追涨诱因。",
        "has_verifiable_facts": "包含可核验事实线索，仍需人工核对来源。" if flag else "缺少可核验事实线索。",
        "is_emotional_comfort": "文本可能主要提供情绪安慰。" if flag else "未发现明显情绪安慰表达。",
        "affected_today_trade": "文章观点可能影响了当天交易动作。" if flag else "无法判断文章是否影响当天交易动作。",
    }
    return reasons[key]


def build_digest(args):
    journal = load_json(args.journal_json)
    title, source_url, text = read_article(args)
    viewpoints = pick_viewpoints(text)
    checks = narrative_checks(text, journal)
    return {
        "source_url": source_url,
        "title": title or "无法判断",
        "viewpoints": viewpoints,
        "narrative_pollution_checks": checks,
        "affected_trade_decision": checks["affected_today_trade"]["flag"],
        "storage_policy": "不保存文章全文，只保存标题、URL、观点摘要和叙事污染检查结果。",
    }


def main():
    parser = argparse.ArgumentParser(description="提取文章观点并做叙事污染检查")
    parser.add_argument("--url", default="")
    parser.add_argument("--text-file", default="")
    parser.add_argument("--text", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--journal-json", default="")
    parser.add_argument("-o", "--output", default="article_digest.json")
    args = parser.parse_args()

    digest = build_digest(args)
    Path(args.output).write_text(json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
