#!/usr/bin/env python3
import argparse
import json


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def simulate_stop_loss(per_stock, threshold):
    rows = []
    original = 0.0
    simulated = 0.0
    for key, item in per_stock.items():
        pnl = item.get("realized_pnl", 0.0)
        cost = item.get("realized_cost", 0.0)
        original += pnl
        floor = -abs(threshold) * cost
        new_pnl = max(pnl, floor) if cost else pnl
        simulated += new_pnl
        if new_pnl != pnl:
            rows.append({"security": key, "original_pnl": round(pnl, 2), "simulated_pnl": round(new_pnl, 2), "estimated_change": round(new_pnl - pnl, 2)})
    return {
        "rule": f"单票亏损达到 {threshold:.0%} 时止损",
        "original_pnl": round(original, 2),
        "simulated_pnl": round(simulated, 2),
        "estimated_change": round(simulated - original, 2),
        "affected_stocks": rows,
        "limitation": "仅用已实现单票结果估算，无法知道盘中是否触发。",
    }


def simulate_take_profit(per_stock, threshold):
    rows = []
    original = 0.0
    simulated = 0.0
    for key, item in per_stock.items():
        pnl = item.get("realized_pnl", 0.0)
        cost = item.get("realized_cost", 0.0)
        original += pnl
        if pnl > threshold * cost and cost:
            locked_half = cost * 0.5 * threshold
            remaining_actual = pnl * 0.5
            new_pnl = locked_half + remaining_actual
            rows.append({"security": key, "original_pnl": round(pnl, 2), "simulated_pnl": round(new_pnl, 2), "estimated_change": round(new_pnl - pnl, 2)})
        else:
            new_pnl = pnl
        simulated += new_pnl
    return {
        "rule": f"盈利达到 {threshold:.0%} 时分批止盈 50%",
        "original_pnl": round(original, 2),
        "simulated_pnl": round(simulated, 2),
        "estimated_change": round(simulated - original, 2),
        "affected_stocks": rows,
        "limitation": "用最终已实现结果反推，可能低估或高估分批止盈效果。",
    }


def simulate_trade_limit(lifecycle, max_trades):
    affected = []
    avoided_loss = 0.0
    missed_profit = 0.0
    for key, item in lifecycle.items():
        trade_count = item.get("trade_count", 0)
        pnl = item.get("realized_pnl", 0.0)
        if trade_count > max_trades:
            estimate = pnl * (trade_count - max_trades) / trade_count if trade_count else 0.0
            if estimate < 0:
                avoided_loss += abs(estimate)
            else:
                missed_profit += estimate
            affected.append({"security": key, "trade_count": trade_count, "pnl": round(pnl, 2), "estimated_removed_result": round(estimate, 2)})
    return {
        "rule": f"单只股票最多交易 {max_trades} 次",
        "possible_loss_reduction": round(avoided_loss, 2),
        "possible_profit_killed": round(missed_profit, 2),
        "affected_stocks": affected,
        "limitation": "按交易次数比例近似估算，不等同于真实重放交易路径。",
    }


def simulate_holding_review(lifecycle, days):
    affected = []
    for key, item in lifecycle.items():
        holding_days = item.get("holding_days")
        if isinstance(holding_days, (int, float)) and holding_days >= days:
            affected.append({"security": key, "holding_days": holding_days, "realized_pnl": item.get("realized_pnl", 0.0)})
    return {
        "rule": f"持仓超过 {days} 天强制复盘",
        "affected_stocks": affected,
        "interpretation": "该规则本身不模拟买卖，只识别需要暂停和复盘的历史样本。",
    }


def simulate_no_add_after_loss(lifecycle, capital, max_loss_ratio):
    affected = []
    for key, item in lifecycle.items():
        events = item.get("events", [])
        buys_after_drawdown = 0
        for event in events:
            if event.get("event") == "加仓" and item.get("realized_pnl", 0.0) < -capital * max_loss_ratio:
                buys_after_drawdown += 1
        if buys_after_drawdown:
            affected.append({
                "security": key,
                "add_count_after_loss": buys_after_drawdown,
                "realized_pnl": item.get("realized_pnl", 0.0),
                "capital_used": round(capital, 2),
            })
    return {
        "rule": f"单票亏损超过总资金 {max_loss_ratio:.1%} 后禁止加仓",
        "affected_stocks": affected,
        "interpretation": "这些样本适合人工验证是否存在越亏越加。",
        "limitation": "若缺少资金余额，总资金使用成交额近似，可信度较低。",
    }


def classify_rules(results):
    reduced = []
    killed = []
    validate = []
    for item in results:
        change = item.get("estimated_change")
        if isinstance(change, (int, float)) and change > 0:
            reduced.append(item["rule"])
        if isinstance(change, (int, float)) and change < 0:
            killed.append(item["rule"])
        if item.get("affected_stocks"):
            validate.append(item["rule"])
    return {
        "哪些规则可能减少亏损": reduced or ["无法判断"],
        "哪些规则可能错杀盈利": killed or ["无法判断"],
        "哪些规则最适合继续人工验证": validate or ["无法判断"],
    }


def main():
    parser = argparse.ArgumentParser(description="Simulate discipline rules on historical realized trades")
    parser.add_argument("metrics_json")
    parser.add_argument("lifecycle_json")
    parser.add_argument("-o", "--output", default="counterfactual_report.json")
    parser.add_argument("--holding-days", type=int, default=20)
    parser.add_argument("--capital-loss-ratio", type=float, default=0.01)
    args = parser.parse_args()

    metrics = load_json(args.metrics_json)
    lifecycle = load_json(args.lifecycle_json)
    per_stock = metrics.get("per_stock_pnl", {})
    summary = metrics.get("summary", {})
    capital = max([0.0] + [abs(v.get("realized_cost", 0.0)) for v in per_stock.values()] + [summary.get("total_buy_amount", 0.0)])
    results = []
    for threshold in (0.03, 0.05, 0.08):
        results.append(simulate_stop_loss(per_stock, threshold))
    for threshold in (0.05, 0.10):
        results.append(simulate_take_profit(per_stock, threshold))
    results.append(simulate_trade_limit(lifecycle, 2))
    results.append(simulate_holding_review(lifecycle, args.holding_days))
    results.append(simulate_no_add_after_loss(lifecycle, capital, args.capital_loss_ratio))

    report = {
        "scope": "只对历史成交结果做反事实模拟，不预测未来走势，不构成买入或卖出建议。",
        "rules": results,
        "summary": classify_rules(results),
    }
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
