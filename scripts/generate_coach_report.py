#!/usr/bin/env python3
import argparse
import html
import json
from pathlib import Path


def e(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def load_json(path, default):
    if not path or not Path(path).exists():
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def money(value):
    if isinstance(value, (int, float)):
        return f"{value:,.2f}"
    return str(value if value is not None else "无法判断")


def security_label(code, item):
    return f"{code} {item.get('security_name', '')}".strip()


def top_stock_lines(per_stock):
    if not per_stock:
        return ["无法判断"]
    rows = sorted(per_stock.items(), key=lambda kv: kv[1].get("realized_pnl", 0))
    lines = []
    for code, item in rows[:8]:
        lines.append(f"{security_label(code, item)}：已实现盈亏 {money(item.get('realized_pnl', 0))}")
    return lines or ["无法判断"]


def triggered_behavior(behavior):
    rows = []
    for name, item in behavior.get("behavior_flags", {}).items():
        if item.get("status") == "触发":
            rows.append(f"{name}（{item.get('severity', '无法判断')}）：{item.get('interpretation', '无法判断')}")
    return rows or ["未发现明显触发项；样本不足处仍需人工复核。"]


def article_lines(digest):
    checks = digest.get("narrative_pollution_checks", {})
    lines = [f"文章：{digest.get('title', '无法判断')}"]
    for name, label in [
        ("reinforces_position_bias", "是否强化已有持仓偏见"),
        ("induces_chasing", "是否诱发追涨"),
        ("has_verifiable_facts", "是否提供可验证事实"),
        ("is_emotional_comfort", "是否只是情绪安慰"),
        ("affected_today_trade", "是否影响当天交易动作"),
    ]:
        item = checks.get(name, {})
        answer = "是" if item.get("flag") else "否/无法判断"
        lines.append(f"{label}：{answer}。{item.get('reason', '')}")
    viewpoints = digest.get("viewpoints") or ["无法判断"]
    lines.append("观点摘要：" + "；".join(viewpoints[:3]))
    return lines


def qualitative(summary, behavior, journal, digest):
    flags = behavior.get("behavior_flags", {})
    if flags.get("疑似补仓摊薄幻觉", {}).get("status") == "触发":
        return "做 T 或补仓可能降低账面成本感受，但加仓风险上升。"
    if flags.get("盈利拿不住", {}).get("status") == "触发" and flags.get("亏损持有过久", {}).get("status") == "触发":
        return "盈利票兑现偏快，亏损票处理偏慢。"
    checks = digest.get("narrative_pollution_checks", {})
    if checks.get("reinforces_position_bias", {}).get("flag"):
        return "交易纪律需要继续观察，文章观点可能强化了持仓偏见。"
    pnl = summary.get("realized_pnl")
    if isinstance(pnl, (int, float)) and pnl >= 0:
        return "今日交易结果为正，但仍需验证模式是否可重复且风险可控。"
    if isinstance(pnl, (int, float)) and pnl < 0:
        return "今日交易结果为负，应优先复盘风险暴露和退出纪律。"
    if journal.get("trading_idea") or journal.get("trade_intent"):
        return "有交易想法记录，但交易数据不足，今日定性无法判断。"
    return "无法判断。"


def discipline_lines(behavior, playbooks, guard):
    lines = []
    for item in playbooks.get("playbooks", {}).get("应避免", [])[:3]:
        lines.append(f"避免重复：{item.get('trigger_condition', '无法判断')}，先写最大风险。")
    for question in guard.get("questions", [])[:3]:
        lines.append(question)
    if not lines:
        lines.append("样本不足，明日前先写清入场理由、退出方式和最大风险。")
    return lines


def reusable_mode(playbooks):
    copied = playbooks.get("playbooks", {}).get("可复制", [])
    pending = playbooks.get("playbooks", {}).get("待验证", [])
    if copied:
        return [f"已存在可复制模式：{item.get('trigger_condition', '无法判断')}（证据 {item.get('evidence_count', 0)} 次）" for item in copied[:5]]
    if pending:
        return [f"待验证模式：{item.get('trigger_condition', '无法判断')}（证据 {item.get('evidence_count', 0)} 次，未满 3 次不升级）" for item in pending[:5]]
    return ["无法判断"]


def build_report(metrics, lifecycle, behavior, journal, digest, playbooks, guard):
    summary = metrics.get("summary", {})
    per_stock = metrics.get("per_stock_pnl", {})
    payload = {
        "scope": "只做历史复盘、行为诊断和风控训练；不荐股、不预测涨跌、不输出买卖建议。",
        "trade_date": journal.get("trade_date", "无法判断"),
        "today_facts": [
            f"总交易次数：{summary.get('total_trades', '无法判断')}",
            f"买入次数：{summary.get('buy_count', '无法判断')}",
            f"卖出次数：{summary.get('sell_count', '无法判断')}",
            f"已实现盈亏：{money(summary.get('realized_pnl'))}",
            f"总费用：{money(summary.get('total_fees'))}",
        ],
        "per_stock_review": top_stock_lines(per_stock),
        "today_intent": [
            f"交易想法：{journal.get('trading_idea') or '无法判断'}",
            f"交易意图：{journal.get('trade_intent') or '无法判断'}",
            f"情绪状态：{journal.get('mood') or '无法判断'}",
        ],
        "today_qualitative": qualitative(summary, behavior, journal, digest),
        "done_well": done_well(summary, behavior),
        "risk_behaviors": triggered_behavior(behavior),
        "article_influence": article_lines(digest),
        "tomorrow_discipline": discipline_lines(behavior, playbooks, guard),
        "reusable_mode": reusable_mode(playbooks),
    }
    return payload


def done_well(summary, behavior):
    lines = []
    if summary.get("sell_count", 0):
        lines.append("有卖出动作记录，可复盘退出质量。")
    if not any(item.get("status") == "触发" and item.get("severity") == "高" for item in behavior.get("behavior_flags", {}).values()):
        lines.append("未发现高严重度行为模式；仍需结合样本量复核。")
    return lines or ["无法判断"]


def markdown_section(title, lines):
    return "## " + title + "\n\n" + "\n".join(f"- {line}" for line in lines) + "\n"


def to_markdown(report):
    sections = [
        "# 每日交易教练报告\n",
        f"> {report['scope']}\n",
        markdown_section("今日交易事实", report["today_facts"]),
        markdown_section("单票动作复盘", report["per_stock_review"]),
        markdown_section("今日交易意图", report["today_intent"]),
        markdown_section("今日定性", [report["today_qualitative"]]),
        markdown_section("做得好的地方", report["done_well"]),
        markdown_section("风险行为", report["risk_behaviors"]),
        markdown_section("文章观点影响", report["article_influence"]),
        markdown_section("明日交易纪律", report["tomorrow_discipline"]),
        markdown_section("是否形成可复用交易模式", report["reusable_mode"]),
    ]
    return "\n".join(sections)


def list_html(lines):
    return "<ul>" + "".join(f"<li>{e(line)}</li>" for line in lines) + "</ul>"


def to_html(report):
    blocks = [
        ("今日交易事实", list_html(report["today_facts"])),
        ("单票动作复盘", list_html(report["per_stock_review"])),
        ("今日交易意图", list_html(report["today_intent"])),
        ("今日定性", f"<p class=\"qualitative\">{e(report['today_qualitative'])}</p>"),
        ("做得好的地方", list_html(report["done_well"])),
        ("风险行为", list_html(report["risk_behaviors"])),
        ("文章观点影响", list_html(report["article_influence"])),
        ("明日交易纪律", list_html(report["tomorrow_discipline"])),
        ("是否形成可复用交易模式", list_html(report["reusable_mode"])),
    ]
    sections = "\n".join(f"<section><h2>{e(title)}</h2>{body}</section>" for title, body in blocks)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>每日交易教练报告</title>
  <style>
    :root {{ --ink:#17202a; --muted:#667085; --line:#d7dee8; --panel:#f8fafc; --accent:#0f766e; --danger:#b42318; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:#fff; line-height:1.65; }}
    main {{ max-width:980px; margin:0 auto; padding:32px 20px 56px; }}
    header {{ border-bottom:1px solid var(--line); padding-bottom:18px; margin-bottom:20px; }}
    h1 {{ margin:0 0 8px; font-size:30px; }}
    h2 {{ font-size:21px; margin:28px 0 10px; }}
    section {{ border-bottom:1px solid var(--line); padding-bottom:16px; }}
    ul {{ padding-left:22px; }}
    li {{ margin:7px 0; }}
    .note {{ color:var(--muted); }}
    .qualitative {{ border-left:4px solid var(--accent); background:var(--panel); padding:12px 14px; }}
    .danger {{ color:var(--danger); }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>每日交易教练报告</h1>
    <p class="note">{e(report['scope'])}</p>
    <p class="note">交易日期：{e(report.get('trade_date', '无法判断'))}</p>
  </header>
  {sections}
</main>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="生成每日交易教练报告")
    parser.add_argument("--metrics", default="metrics.json")
    parser.add_argument("--lifecycle", default="trade_lifecycle.json")
    parser.add_argument("--behavior", default="behavior_flags.json")
    parser.add_argument("--journal", default="daily_journal.json")
    parser.add_argument("--article", default="article_digest.json")
    parser.add_argument("--playbooks", default="local_state/playbooks.json")
    parser.add_argument("--guard", default="pre_trade_guard.json")
    parser.add_argument("--json-output", default="daily_coach_report.json")
    parser.add_argument("--markdown-output", default="daily_coach_report.md")
    parser.add_argument("--html-output", default="daily_coach_report.html")
    args = parser.parse_args()

    report = build_report(
        load_json(args.metrics, {}),
        load_json(args.lifecycle, {}),
        load_json(args.behavior, {}),
        load_json(args.journal, {}),
        load_json(args.article, {}),
        load_json(args.playbooks, {}),
        load_json(args.guard, {}),
    )
    Path(args.json_output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.markdown_output).write_text(to_markdown(report), encoding="utf-8")
    Path(args.html_output).write_text(to_html(report), encoding="utf-8")
    print(f"wrote {args.json_output}")
    print(f"wrote {args.markdown_output}")
    print(f"wrote {args.html_output}")


if __name__ == "__main__":
    main()
