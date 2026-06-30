#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_trades(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def money(value):
    if isinstance(value, (int, float)):
        return f"{value:,.2f}"
    return str(value)


def percent(value):
    if isinstance(value, (int, float)):
        return f"{value:.2%}"
    return str(value)


def build_name_map(per_stock, lifecycle):
    mapping = {}
    for code, item in per_stock.items():
        name = item.get("security_name", "")
        if name:
            mapping[str(code)] = name
    for code, item in lifecycle.items():
        name = item.get("security_name", "")
        if name and str(code) not in mapping:
            mapping[str(code)] = name
    return mapping


def security_label(code, name=None, name_map=None):
    if code is None:
        return "无法判断"
    code_text = str(code)
    name_text = name or (name_map or {}).get(code_text, "")
    return f"{code_text} {name_text}".strip()


def label_text(text, name_map):
    output = str(text)
    for code in sorted(name_map, key=len, reverse=True):
        label = security_label(code, name_map=name_map)
        output = output.replace(code, label)
    return output


def line_items(items):
    if not items:
        return "- 无明显证据"
    return "\n".join(f"- {item}" for item in items)


def top_stocks(per_stock, name_map, reverse=True, n=5):
    rows = sorted(per_stock.items(), key=lambda kv: kv[1].get("realized_pnl", 0), reverse=reverse)
    rows = [row for row in rows if (row[1].get("realized_pnl", 0) > 0 if reverse else row[1].get("realized_pnl", 0) < 0)]
    if not rows:
        return "- 无法判断"
    return "\n".join(f"- {security_label(key, value.get('security_name', ''), name_map)}: {money(value.get('realized_pnl', 0))}" for key, value in rows[:n])


def triggered_flags(flags, name_map):
    rows = []
    for name, item in flags.items():
        if item.get("status") == "触发":
            evidence = "；".join(label_text(x, name_map) for x in (item.get("evidence") or ["无"]))
            rows.append(f"- {name}（{item.get('severity')}）：{item.get('interpretation')} 证据：{evidence}")
    return "\n".join(rows) if rows else "- 未触发明显行为风险；样本不足处仍需人工复核。"


def risk_list(flags, name_map):
    rows = []
    for name, item in flags.items():
        if item.get("status") in ("触发", "无法判断"):
            rows.append(f"- {name}: {item.get('status')}。{label_text(item.get('limitation') or item.get('interpretation'), name_map)}")
    return "\n".join(rows) if rows else "- 暂无突出风险。"


def render_counterfactual(counterfactual, name_map):
    summary = counterfactual.get("summary", {})
    rows = [
        "可能减少亏损：" + "、".join(summary.get("哪些规则可能减少亏损", ["无法判断"])),
        "可能错杀盈利：" + "、".join(summary.get("哪些规则可能错杀盈利", ["无法判断"])),
        "适合人工验证：" + "、".join(summary.get("哪些规则最适合继续人工验证", ["无法判断"])),
    ]
    details = []
    for rule in counterfactual.get("rules", []):
        affected = []
        for stock in rule.get("affected_stocks", []):
            if stock.get("security"):
                affected.append(security_label(stock.get("security"), name_map=name_map))
        affected_text = f" 样本：{'、'.join(affected)}。" if affected else ""
        change = rule.get("estimated_change")
        if isinstance(change, (int, float)):
            details.append(f"- {rule.get('rule')}: 估算变化 {money(change)}。{affected_text}{label_text(rule.get('limitation', ''), name_map)}")
        else:
            details.append(f"- {rule.get('rule')}: 影响样本 {len(rule.get('affected_stocks', []))} 个。{affected_text}{label_text(rule.get('interpretation', ''), name_map)}")
    return "\n".join(rows + [""] + details)


def data_quality_section(metrics, trades):
    warnings = []
    if metrics.get("data_warnings", {}).get("unmatched_sells"):
        warnings.append("存在无法匹配买入记录的卖出，可能说明导入区间前已有持仓。")
    if not any(float(r.get("total_fee") or 0) > 0 for r in trades):
        warnings.append("费用字段全部为 0，手续费消耗可能被低估。")
    if not any(float(r.get("cash_balance") or 0) > 0 for r in trades):
        warnings.append("缺少有效资金余额，仓位和资金风险只能近似或无法判断。")
    if not any(r.get("side") == "SELL" for r in trades):
        warnings.append("没有卖出记录，已实现盈亏、胜率和持仓天数多为无法判断。")
    return line_items(warnings) if warnings else "- 字段可支持基础历史复盘。仍需确认样本覆盖完整周期。"


def build_report(trades, metrics, lifecycle, behavior, counterfactual):
    summary = metrics["summary"]
    per_stock = metrics.get("per_stock_pnl", {})
    name_map = build_name_map(per_stock, lifecycle)
    flags = behavior.get("behavior_flags", {})
    monthly = metrics.get("monthly_pnl", {})
    month_lines = "\n".join(f"- {month}: {money(pnl)}" for month, pnl in monthly.items()) or "- 无法判断"
    most_loss = summary.get("max_single_stock_loss", {})
    most_profit = summary.get("max_single_stock_profit", {})

    return f"""# 个人交易复盘报告

> 本报告只基于用户提供的历史成交数据做复盘，不荐股、不预测未来涨跌，也不输出买入或卖出某只股票的建议。若数据不足，相关结论标注为 `无法判断`。

## 数据概览

- 成交记录数：{summary.get("total_trades")}
- 买入次数：{summary.get("buy_count")}
- 卖出次数：{summary.get("sell_count")}
- 涉及股票数：{summary.get("stock_count")}
- 数据质量：
{data_quality_section(metrics, trades)}

## 核心指标

- 总买入金额：{money(summary.get("total_buy_amount"))}
- 总卖出金额：{money(summary.get("total_sell_amount"))}
- 总费用：{money(summary.get("total_fees"))}
- 已实现盈亏：{money(summary.get("realized_pnl"))}
- 胜率：{percent(summary.get("win_rate"))}
- 平均盈利：{money(summary.get("average_profit"))}
- 平均亏损：{money(summary.get("average_loss"))}
- 盈亏比：{summary.get("profit_loss_ratio")}
- 手续费占成交额比例：{percent(summary.get("fee_ratio_to_turnover"))}

## 盈利来源

最大单票盈利：{security_label(most_profit.get("security"), name_map=name_map)}，{money(most_profit.get("amount"))}

{top_stocks(per_stock, name_map, reverse=True)}

## 亏损来源

最大单票亏损：{security_label(most_loss.get("security"), name_map=name_map)}，{money(most_loss.get("amount"))}

{top_stocks(per_stock, name_map, reverse=False)}

月度盈亏：

{month_lines}

## 行为模式

{triggered_flags(flags, name_map)}

## 风险清单

{risk_list(flags, name_map)}

## 反事实模拟

{render_counterfactual(counterfactual, name_map)}

## 五角色复盘

### 角色一：交易导师

- 最关键的 5 个指标：已实现盈亏、单票最大亏损、平均盈利/平均亏损、手续费占比、同一股票交易次数。
- 这份交割单首先要看亏损是否集中，其次看盈利是否足以覆盖亏损和费用。
- 不能过度解读的部分：没有行情数据时，追高只能用成交价近似；没有完整历史持仓时，成本和持仓天数可能偏差；没有资金余额时，仓位风险无法准确判断。

### 角色二：数据分析师

- 盈利主要来自：{security_label(most_profit.get("security"), name_map=name_map)}，金额 {money(most_profit.get("amount"))}。
- 亏损主要来自：{security_label(most_loss.get("security"), name_map=name_map)}，金额 {money(most_loss.get("amount"))}。
- 最拖累结果的行为优先看：{", ".join([name for name, item in flags.items() if item.get("status") == "触发"][:3]) or "无法判断"}。

### 角色三：风控教练

- 下一阶段先控制单票最大亏损，再控制交易频率和加仓条件。
- 若某只股票亏损扩大后仍继续加仓，必须在加仓前写出原计划、失效条件和最大亏损额度。
- 持仓超过复盘阈值时，不自动交易，但必须暂停新增同票交易并复盘。

### 角色四：市场对手盘

- 市场最容易惩罚的是没有退出条件的交易：亏损可以拖长，盈利却可能很快兑现。
- 如果同一股票反复交易且结果为负，说明交易动作本身没有形成优势，反而增加了费用和判断噪音。
- 如果最大亏损吞噬多笔小盈利，说明真正的问题不是选中几次盈利，而是亏损失控。

### 角色五：纪律监督员

- 未来 10 笔交易前必须回答：买入理由是什么、失效条件是什么、最大允许亏损是多少、是否已有同票持仓、是否违反交易频率上限、是否刚发生连续亏损、是否因为追回亏损而下单、是否因为卖飞而追高、是否记录了卖出计划、这笔交易不做会损失什么。
- 禁止交易条件：数据未记录、没有退出条件、单票亏损超过规则仍想加仓、同日已多次冲动交易、无法说清交易计划。
- 交易后复盘模板：计划是什么、实际执行是什么、盈亏来自价格还是仓位、是否违反纪律、下一笔同类交易要删掉哪个动作。

## 下一阶段交易纪律

- 单票亏损达到 -3%、-5%、-8% 分层复盘，具体是否止损由人工验证历史错杀情况。
- 单只股票在一个复盘周期内最多交易 2 次，超过必须停手写复盘。
- 加仓前必须确认不是为了摊薄亏损感受，而是符合事前计划。
- 手续费占比升高时，减少低确定性短线交易。

## 买入前检查清单

- 这笔交易是否有书面理由？
- 如果判断错了，哪一个条件说明该退出？
- 单票最大亏损占总资金多少？无法计算则写 `无法判断`。
- 是否刚刚在同一股票上亏损或卖飞？
- 买入后是否会违反交易频率或加仓规则？

## 卖出前检查清单

- 卖出是因为计划触发，还是因为情绪波动？
- 如果盈利，是否过早兑现？如果亏损，是否已经拖延？
- 卖出后是否准备更高价格追回？如果是，先暂停复盘。
- 卖出是否会让同一股票形成反复买卖循环？

## 下次复盘要回答的问题

- 哪一只股票贡献了最多亏损，原因是价格判断、仓位、频率还是退出纪律？
- 最大亏损是否超过了事前规则？
- 哪些盈利被过早兑现？
- 哪些交易完全没有必要？
- 哪条纪律规则最值得继续人工验证？
"""


def main():
    parser = argparse.ArgumentParser(description="Generate a Markdown trade review report")
    parser.add_argument("cleaned_trades", nargs="?", default="cleaned_trades.csv")
    parser.add_argument("metrics_json", nargs="?", default="metrics.json")
    parser.add_argument("lifecycle_json", nargs="?", default="trade_lifecycle.json")
    parser.add_argument("behavior_json", nargs="?", default="behavior_flags.json")
    parser.add_argument("counterfactual_json", nargs="?", default="counterfactual_report.json")
    parser.add_argument("-o", "--output", default="trade_review_report.md")
    args = parser.parse_args()
    report = build_report(
        load_trades(args.cleaned_trades),
        load_json(args.metrics_json),
        load_json(args.lifecycle_json),
        load_json(args.behavior_json),
        load_json(args.counterfactual_json),
    )
    Path(args.output).write_text(report, encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
