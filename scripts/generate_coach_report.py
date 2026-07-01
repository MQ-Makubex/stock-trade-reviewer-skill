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


def amount_units(value, unit=50000):
    if not isinstance(value, (int, float)) or unit <= 0:
        return "无法判断"
    units = abs(value) / unit
    if units < 0.25:
        return "<0.5单位"
    rounded = round(units * 2) / 2
    if rounded.is_integer():
        return f"约{int(rounded)}单位"
    return f"约{rounded:.1f}单位"


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


def macro_lens_lines(macro_lenses):
    lenses = macro_lenses.get("macro_lenses", []) if isinstance(macro_lenses, dict) else []
    source = macro_lenses.get("source", {}) if isinstance(macro_lenses, dict) else {}
    if not lenses:
        return ["无法判断：尚未更新宏观镜片，或网页抓取没有得到可用文章。"]
    lines = []
    if source.get("name"):
        lines.append(f"宏观镜片来源：{source.get('name')}，更新时间：{source.get('updated_at', '无法判断')}。")
    for item in lenses[:5]:
        risks = "、".join(item.get("risk_tags", [])[:3]) or "未见明显叙事风险"
        lines.append(f"{item.get('lens', '宏观观察')}：{item.get('observation', '无法判断')}（风险标签：{risks}）")
    return lines


def journal_text(journal):
    fields = ["trading_idea", "trade_intent", "plan", "review_note", "mood"]
    return "\n".join(str(journal.get(field, "") or "") for field in fields)


def market_context_lines(journal, digest, macro_lenses):
    text = journal_text(journal)
    lines = []
    if any(word in text for word in ["大盘", "指数", "上涨", "回调", "市场", "风格"]):
        lines.append(f"用户盘面观察：{text[:220]}")
    else:
        lines.append("用户未提供足够盘面观察，市场环境无法独立判断。")
    if any(word in text for word in ["看不懂", "不确定", "不知道"]):
        lines.append("教练判断：当前主观状态是不确定，优先降低交易频率和仓位冲动，而不是用宏观叙事替代规则。")
    if any(word in text for word in ["科技", "医药", "白马", "防守", "低位"]):
        lines.append("教练判断：已出现风格切换叙事，但只能作为环境观察，不能直接推出单票买卖动作。")
    checks = digest.get("narrative_pollution_checks", {}) if isinstance(digest, dict) else {}
    if checks.get("reinforces_position_bias", {}).get("flag"):
        lines.append("文章影响：存在强化已有持仓偏见的风险，明日计划必须回到止损、仓位和验证条件。")
    lenses = macro_lenses.get("macro_lenses", []) if isinstance(macro_lenses, dict) else []
    if lenses:
        first = lenses[0]
        lines.append(f"宏观镜片提醒：{first.get('lens', '宏观观察')} - {first.get('observation', '无法判断')}")
    return lines or ["无法判断"]


def coach_reason_lines(summary, behavior, journal, digest, macro_lenses):
    lines = []
    total_trades = summary.get("total_trades")
    if isinstance(total_trades, int):
        lines.append(f"交易事实依据：今日有 {total_trades} 笔成交，因此判断先看行为质量，再看结果盈亏。")
    pnl = summary.get("realized_pnl")
    if isinstance(pnl, (int, float)):
        direction = "为正" if pnl >= 0 else "为负"
        lines.append(f"结果依据：已实现盈亏{direction}，但单日结果不能证明模式可复制。")
    triggered = [
        name for name, item in behavior.get("behavior_flags", {}).items()
        if item.get("status") == "触发"
    ]
    if triggered:
        lines.append("行为依据：触发了 " + "、".join(triggered[:5]) + "，明日计划必须先处理这些风险。")
    else:
        lines.append("行为依据：未发现明显触发项，但样本不足时不能过度解读。")
    if journal.get("trading_idea") or journal.get("trade_intent"):
        lines.append("主观依据：你记录了交易想法，因此报告会检查“计划动作”和“临盘情绪”是否一致。")
    if macro_lenses.get("macro_lenses"):
        lines.append("宏观依据：宏观镜片只用于解释市场环境，不覆盖单票止损和仓位规则。")
    if digest.get("viewpoints"):
        lines.append("文章依据：文章观点只作为叙事污染检查输入，不作为买卖理由。")
    return lines or ["无法判断"]


def tomorrow_plan_lines(journal, behavior, playbooks, guard):
    text = journal_text(journal)
    lines = []
    if any(word in text for word in ["5日", "五日", "5 日"]):
        lines.append("条件计划：若价格回到 5 日均线附近，只允许按事前定义的试错仓执行，并先写清失败条件。")
    if any(word in text for word in ["10日", "十日", "10 日", "止损"]):
        lines.append("条件计划：若尾盘有效跌破 10 日线，或跌破日内均线且两次反弹无法站回，按规则处理风险。")
    if any(word in text for word in ["看不懂", "不确定", "不知道", "风格"]):
        lines.append("条件计划：若大盘和风格仍无法判断，明日先减少临盘切换，等待市场确认后再评估。")
    if any(word in text for word in ["做T", "做 T", "卖飞"]):
        lines.append("条件计划：做 T 只允许服务于既定仓位和风险规则，不能用来修正卖飞焦虑。")
    for question in guard.get("questions", [])[:2]:
        lines.append(f"买前反问：{question}")
    if not lines:
        lines.extend(discipline_lines(behavior, playbooks, guard))
    return lines or ["无法判断"]


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


def build_report(metrics, lifecycle, behavior, journal, digest, playbooks, guard, macro_lenses=None):
    macro_lenses = macro_lenses or {}
    summary = metrics.get("summary", {})
    per_stock = metrics.get("per_stock_pnl", {})
    tomorrow_plan = tomorrow_plan_lines(journal, behavior, playbooks, guard)
    payload = {
        "scope": "只做历史复盘、行为诊断和风控训练；不荐股、不预测涨跌、不输出买卖建议。",
        "trade_date": journal.get("trade_date", "无法判断"),
        "market_context": market_context_lines(journal, digest, macro_lenses),
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
        "coach_reasoning": coach_reason_lines(summary, behavior, journal, digest, macro_lenses),
        "done_well": done_well(summary, behavior),
        "risk_behaviors": triggered_behavior(behavior),
        "article_influence": article_lines(digest),
        "macro_lens": macro_lens_lines(macro_lenses),
        "tomorrow_discipline": tomorrow_plan,
        "reusable_mode": reusable_mode(playbooks),
    }
    payload["xueqiu_post"] = build_xueqiu_post(payload, metrics, journal)
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
        markdown_section("市场情况判断", report["market_context"]),
        markdown_section("今日交易事实", report["today_facts"]),
        markdown_section("单票动作复盘", report["per_stock_review"]),
        markdown_section("今日交易意图", report["today_intent"]),
        markdown_section("今日定性", [report["today_qualitative"]]),
        markdown_section("教练判断理由", report["coach_reasoning"]),
        markdown_section("做得好的地方", report["done_well"]),
        markdown_section("风险行为", report["risk_behaviors"]),
        markdown_section("文章观点影响", report["article_influence"]),
        markdown_section("宏观镜片", report["macro_lens"]),
        markdown_section("明日交易纪律", report["tomorrow_discipline"]),
        markdown_section("是否形成可复用交易模式", report["reusable_mode"]),
        "## 雪球发布版草稿\n\n```markdown\n" + to_xueqiu_markdown(report) + "```\n",
    ]
    return "\n".join(sections)


def list_html(lines):
    return "<ul>" + "".join(f"<li>{e(line)}</li>" for line in lines) + "</ul>"


def to_html(report):
    blocks = [
        ("市场情况判断", list_html(report["market_context"])),
        ("今日交易事实", list_html(report["today_facts"])),
        ("单票动作复盘", list_html(report["per_stock_review"])),
        ("今日交易意图", list_html(report["today_intent"])),
        ("今日定性", f"<p class=\"qualitative\">{e(report['today_qualitative'])}</p>"),
        ("教练判断理由", list_html(report["coach_reasoning"])),
        ("做得好的地方", list_html(report["done_well"])),
        ("风险行为", list_html(report["risk_behaviors"])),
        ("文章观点影响", list_html(report["article_influence"])),
        ("宏观镜片", list_html(report["macro_lens"])),
        ("明日交易纪律", list_html(report["tomorrow_discipline"])),
        ("是否形成可复用交易模式", list_html(report["reusable_mode"])),
        ("雪球发布版草稿", list_html(report["xueqiu_post"]["lines"])),
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


def stock_action_lines(metrics):
    per_stock = metrics.get("per_stock_pnl", {})
    if not per_stock:
        return ["单票动作：无法判断。"]
    lines = []
    for code, item in sorted(per_stock.items(), key=lambda kv: kv[1].get("trade_count", 0), reverse=True)[:8]:
        label = security_label(code, item)
        turnover_basis = abs(item.get("sell_revenue", 0) or 0) + abs(item.get("realized_cost", 0) or 0)
        unit_text = amount_units(turnover_basis)
        pnl = item.get("realized_pnl")
        result = "正贡献" if isinstance(pnl, (int, float)) and pnl > 0 else "负贡献" if isinstance(pnl, (int, float)) and pnl < 0 else "结果无法判断"
        lines.append(f"{label}：{item.get('trade_count', '无法判断')} 笔成交，成交规模{unit_text}，已实现结果为{result}。")
    return lines


def build_xueqiu_post(report, metrics, journal):
    date = report.get("trade_date") or "无法判断"
    lines = [
        f"# {date} 每日复盘与明日计划",
        "",
        "仅为个人交易复盘，不构成投资建议。",
        "",
        "## 今日市场观察",
    ]
    lines.extend(f"- {line}" for line in report.get("market_context", []))
    lines.extend(["", "## 今日操作复盘"])
    lines.extend(f"- {line}" for line in stock_action_lines(metrics))
    lines.extend(["", "## 今日定性"])
    lines.append(f"- {report.get('today_qualitative', '无法判断')}")
    lines.extend(["", "## 教练判断与理由"])
    lines.extend(f"- {line}" for line in report.get("coach_reasoning", []))
    lines.extend(["", "## 明日计划"])
    lines.extend(f"- {line}" for line in report.get("tomorrow_discipline", []))
    lines.extend(["", "## 复盘提醒"])
    plan = journal.get("plan") or "无法判断"
    lines.append(f"- 原计划/备注：{plan}")
    lines.append("- 明日所有动作只按条件触发，不做确定性预测。")
    return {
        "title": f"{date} 每日复盘与明日计划",
        "lines": lines,
        "storage_policy": "发布版不展示资金余额或账户信息；成交金额默认转换为单位表达。",
    }


def to_xueqiu_markdown(report):
    return "\n".join(report["xueqiu_post"]["lines"]) + "\n"


def to_xueqiu_html(report):
    body = []
    in_list = False
    for line in report["xueqiu_post"]["lines"]:
        if line.startswith("# "):
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append(f"<h1>{e(line[2:])}</h1>")
        elif line.startswith("## "):
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append(f"<h2>{e(line[3:])}</h2>")
        elif line.startswith("- "):
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{e(line[2:])}</li>")
        elif line.strip():
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append(f"<p>{e(line)}</p>")
    if in_list:
        body.append("</ul>")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{e(report["xueqiu_post"]["title"])}</title>
  <style>
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:#17202a; line-height:1.75; background:#fff; }}
    main {{ max-width:860px; margin:0 auto; padding:32px 20px 56px; }}
    h1 {{ font-size:30px; margin:0 0 14px; }}
    h2 {{ font-size:22px; margin:28px 0 10px; border-bottom:1px solid #d7dee8; padding-bottom:6px; }}
    li {{ margin:7px 0; }}
    p {{ color:#475467; }}
  </style>
</head>
<body><main>
{chr(10).join(body)}
</main></body>
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
    parser.add_argument("--macro-lenses", default="local_state/macro_lenses.json")
    parser.add_argument("--json-output", default="daily_coach_report.json")
    parser.add_argument("--markdown-output", default="daily_coach_report.md")
    parser.add_argument("--html-output", default="daily_coach_report.html")
    parser.add_argument("--xueqiu-markdown-output", default="daily_xueqiu_post.md")
    parser.add_argument("--xueqiu-html-output", default="daily_xueqiu_post.html")
    args = parser.parse_args()

    report = build_report(
        load_json(args.metrics, {}),
        load_json(args.lifecycle, {}),
        load_json(args.behavior, {}),
        load_json(args.journal, {}),
        load_json(args.article, {}),
        load_json(args.playbooks, {}),
        load_json(args.guard, {}),
        load_json(args.macro_lenses, {}),
    )
    Path(args.json_output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.markdown_output).write_text(to_markdown(report), encoding="utf-8")
    Path(args.html_output).write_text(to_html(report), encoding="utf-8")
    Path(args.xueqiu_markdown_output).write_text(to_xueqiu_markdown(report), encoding="utf-8")
    Path(args.xueqiu_html_output).write_text(to_xueqiu_html(report), encoding="utf-8")
    print(f"wrote {args.json_output}")
    print(f"wrote {args.markdown_output}")
    print(f"wrote {args.html_output}")
    print(f"wrote {args.xueqiu_markdown_output}")
    print(f"wrote {args.xueqiu_html_output}")


if __name__ == "__main__":
    main()
