#!/usr/bin/env python3
import argparse
import html
import json
import re
from pathlib import Path


def e(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_text(path):
    p = Path(path)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def money(value):
    if isinstance(value, (int, float)):
        return f"{value:,.2f}"
    return str(value)


def percent(value):
    if isinstance(value, (int, float)):
        return f"{value:.2%}"
    return str(value)


def list_items(items):
    if not items:
        return "<li>无法判断</li>"
    return "".join(f"<li>{e(item)}</li>" for item in items)


def metric_card(label, value):
    return f'<div class="metric"><span>{e(label)}</span><strong>{e(value)}</strong></div>'


def scan_sensitive(obj, path="root"):
    findings = []
    sensitive_keys = ["姓名", "身份证", "手机号", "资金账号", "资金帐号", "客户号", "股东账号", "股东帐号", "银行卡", "营业部", "地址"]
    id_pattern = re.compile(r"(?<!\d)[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)")
    phone_pattern = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
    bank_pattern = re.compile(r"(?<!\d)\d{13,19}(?!\d)")

    if isinstance(obj, dict):
        for key, value in obj.items():
            key_text = str(key)
            if any(token in key_text for token in sensitive_keys):
                findings.append({"path": path, "type": "sensitive_key"})
            findings.extend(scan_sensitive(value, f"{path}.{key_text}"))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            findings.extend(scan_sensitive(value, f"{path}[{index}]"))
    else:
        text = str(obj)
        if id_pattern.search(text):
            findings.append({"path": path, "type": "id_card_like"})
        if phone_pattern.search(text):
            findings.append({"path": path, "type": "phone_like"})
        if bank_pattern.search(text):
            findings.append({"path": path, "type": "long_number_like"})
    return findings


def top_stocks(per_stock, reverse=True):
    rows = sorted(per_stock.items(), key=lambda kv: kv[1].get("realized_pnl", 0), reverse=reverse)
    filtered = [row for row in rows if (row[1].get("realized_pnl", 0) > 0 if reverse else row[1].get("realized_pnl", 0) < 0)]
    if not filtered:
        return "<li>无法判断</li>"
    parts = []
    for code, item in filtered[:5]:
        parts.append(f"<li><strong>{e(code)}</strong> {e(item.get('security_name', ''))}: {e(money(item.get('realized_pnl', 0)))}</li>")
    return "".join(parts)


def behavior_items(flags):
    parts = []
    for name, item in flags.items():
        evidence = "；".join(str(x) for x in item.get("evidence", []) if x)
        parts.append(
            "<li>"
            f"<strong>{e(name)}</strong> "
            f"<span class=\"tag\">{e(item.get('status', '无法判断'))}</span> "
            f"<span class=\"tag muted\">{e(item.get('severity', ''))}</span>"
            f"<p>{e(item.get('interpretation', ''))}</p>"
            f"<small>{e(evidence or item.get('limitation', ''))}</small>"
            "</li>"
        )
    return "".join(parts) if parts else "<li>无法判断</li>"


def counterfactual_items(counterfactual):
    parts = []
    for rule in counterfactual.get("rules", []):
        change = rule.get("estimated_change")
        summary = f"估算变化 {money(change)}" if isinstance(change, (int, float)) else f"影响样本 {len(rule.get('affected_stocks', []))} 个"
        parts.append(
            "<li>"
            f"<strong>{e(rule.get('rule', ''))}</strong>"
            f"<p>{e(summary)}</p>"
            f"<small>{e(rule.get('limitation') or rule.get('interpretation') or '')}</small>"
            "</li>"
        )
    return "".join(parts) if parts else "<li>无法判断</li>"


def extract_markdown_section(markdown, heading):
    pattern = re.compile(rf"^##+\s+{re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(markdown)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+", markdown[start:], re.MULTILINE)
    end = start + next_match.start() if next_match else len(markdown)
    return markdown[start:end].strip()


def markdown_lines_to_html(markdown):
    if not markdown:
        return "<p>无法判断</p>"
    output = []
    in_list = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            if in_list:
                output.append("</ul>")
                in_list = False
            continue
        if line.startswith("### "):
            if in_list:
                output.append("</ul>")
                in_list = False
            output.append(f"<h3>{e(line[4:])}</h3>")
        elif line.startswith("- "):
            if not in_list:
                output.append("<ul>")
                in_list = True
            output.append(f"<li>{e(line[2:])}</li>")
        else:
            if in_list:
                output.append("</ul>")
                in_list = False
            output.append(f"<p>{e(line)}</p>")
    if in_list:
        output.append("</ul>")
    return "\n".join(output)


def build_html(metrics, lifecycle, behavior, counterfactual, markdown):
    summary = metrics.get("summary", {})
    per_stock = metrics.get("per_stock_pnl", {})
    flags = behavior.get("behavior_flags", {})
    sensitive_findings = scan_sensitive({
        "metrics": metrics,
        "trade_lifecycle": lifecycle,
        "behavior_flags": behavior,
        "counterfactual_report": counterfactual,
        "markdown": markdown,
    })
    warning = ""
    if sensitive_findings:
        warning = f'<div class="warning"><strong>隐私警告：</strong>报告输入中发现 {e(len(sensitive_findings))} 处疑似敏感字段或长数字。请先回到本地 CSV 执行隐私检查。</div>'

    metrics_html = "".join([
        metric_card("总交易次数", summary.get("total_trades", "无法判断")),
        metric_card("买入次数", summary.get("buy_count", "无法判断")),
        metric_card("卖出次数", summary.get("sell_count", "无法判断")),
        metric_card("涉及股票数", summary.get("stock_count", "无法判断")),
        metric_card("已实现盈亏", money(summary.get("realized_pnl", "无法判断"))),
        metric_card("胜率", percent(summary.get("win_rate", "无法判断"))),
        metric_card("平均盈利", money(summary.get("average_profit", "无法判断"))),
        metric_card("平均亏损", money(summary.get("average_loss", "无法判断"))),
        metric_card("盈亏比", summary.get("profit_loss_ratio", "无法判断")),
        metric_card("费用占成交额", percent(summary.get("fee_ratio_to_turnover", "无法判断"))),
    ])

    role_section = extract_markdown_section(markdown, "五角色复盘")
    discipline_section = extract_markdown_section(markdown, "下一阶段交易纪律")
    buy_section = extract_markdown_section(markdown, "买入前检查清单")
    sell_section = extract_markdown_section(markdown, "卖出前检查清单")

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>个人交易复盘报告</title>
  <style>
    :root {{ color-scheme: light; --ink:#17202a; --muted:#687385; --line:#dfe5ec; --panel:#f7f9fb; --accent:#0f766e; --danger:#b42318; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:#fff; line-height:1.6; }}
    main {{ max-width:1040px; margin:0 auto; padding:32px 20px 56px; }}
    header {{ border-bottom:1px solid var(--line); padding-bottom:20px; margin-bottom:24px; }}
    h1 {{ font-size:30px; margin:0 0 8px; }}
    h2 {{ font-size:21px; margin:32px 0 12px; padding-top:8px; }}
    h3 {{ font-size:17px; margin:18px 0 8px; }}
    p {{ margin:8px 0; }}
    .note {{ color:var(--muted); }}
    .warning {{ border:1px solid #f3b4ad; background:#fff1f0; color:var(--danger); padding:12px 14px; border-radius:8px; margin:18px 0; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; }}
    .metric {{ border:1px solid var(--line); border-radius:8px; padding:12px; background:var(--panel); }}
    .metric span {{ display:block; color:var(--muted); font-size:13px; }}
    .metric strong {{ display:block; margin-top:4px; font-size:18px; }}
    .columns {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:18px; }}
    section {{ border-bottom:1px solid var(--line); padding-bottom:18px; }}
    ul {{ padding-left:21px; }}
    li {{ margin:7px 0; }}
    .cards {{ list-style:none; padding:0; display:grid; gap:10px; }}
    .cards li {{ border:1px solid var(--line); border-radius:8px; padding:12px; background:#fff; }}
    .tag {{ display:inline-block; font-size:12px; border:1px solid var(--accent); color:var(--accent); padding:1px 7px; border-radius:999px; margin-left:6px; }}
    .tag.muted {{ border-color:var(--line); color:var(--muted); }}
    small {{ color:var(--muted); }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>个人交易复盘报告</h1>
    <p class="note">本报告只基于历史成交数据做复盘，不荐股、不预测未来涨跌，也不提供买入或卖出建议。</p>
    {warning}
  </header>

  <section>
    <h2>数据概览与核心指标</h2>
    <div class="grid">{metrics_html}</div>
  </section>

  <section>
    <h2>盈利来源</h2>
    <ul>{top_stocks(per_stock, reverse=True)}</ul>
  </section>

  <section>
    <h2>亏损来源</h2>
    <ul>{top_stocks(per_stock, reverse=False)}</ul>
  </section>

  <section>
    <h2>行为模式</h2>
    <ul class="cards">{behavior_items(flags)}</ul>
  </section>

  <section>
    <h2>风险提示</h2>
    <ul>{list_items([name + "：" + item.get("status", "无法判断") + "。" + (item.get("limitation") or item.get("interpretation") or "") for name, item in flags.items() if item.get("status") in ("触发", "无法判断")])}</ul>
  </section>

  <section>
    <h2>反事实模拟</h2>
    <ul class="cards">{counterfactual_items(counterfactual)}</ul>
  </section>

  <section>
    <h2>五角色复盘</h2>
    {markdown_lines_to_html(role_section)}
  </section>

  <section>
    <h2>下一阶段交易纪律</h2>
    {markdown_lines_to_html(discipline_section)}
  </section>

  <section class="columns">
    <div>
      <h2>买入前检查清单</h2>
      {markdown_lines_to_html(buy_section)}
    </div>
    <div>
      <h2>卖出前检查清单</h2>
      {markdown_lines_to_html(sell_section)}
    </div>
  </section>
</main>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="生成本地单文件 HTML 交易复盘报告")
    parser.add_argument("metrics_json", nargs="?", default="metrics.json")
    parser.add_argument("lifecycle_json", nargs="?", default="trade_lifecycle.json")
    parser.add_argument("behavior_json", nargs="?", default="behavior_flags.json")
    parser.add_argument("counterfactual_json", nargs="?", default="counterfactual_report.json")
    parser.add_argument("--markdown", default="trade_review_report.md")
    parser.add_argument("-o", "--output", default="trade_review_report.html")
    args = parser.parse_args()

    html_text = build_html(
        load_json(args.metrics_json),
        load_json(args.lifecycle_json),
        load_json(args.behavior_json),
        load_json(args.counterfactual_json),
        load_text(args.markdown),
    )
    Path(args.output).write_text(html_text, encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
