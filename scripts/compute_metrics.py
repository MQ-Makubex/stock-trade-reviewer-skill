#!/usr/bin/env python3
import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime


def fnum(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def load_trades(path):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    rows.sort(key=lambda r: (r.get("trade_date", ""), int(float(r.get("source_row") or 0))))
    return rows


def stock_key(row):
    return row.get("security_code") or row.get("security_name") or "UNKNOWN"


def month_of(row):
    text = row.get("trade_date", "")
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").strftime("%Y-%m")
    except ValueError:
        return "无法判断"


def fifo_realized(trades):
    lots = defaultdict(list)
    per_stock = defaultdict(lambda: {"realized_pnl": 0.0, "realized_cost": 0.0, "sell_revenue": 0.0, "trade_count": 0})
    monthly = defaultdict(float)
    unmatched_sells = []

    for row in trades:
        key = stock_key(row)
        side = row.get("side")
        qty = fnum(row.get("quantity"))
        amount = abs(fnum(row.get("trade_amount")))
        fee = fnum(row.get("total_fee"))
        per_stock[key]["security_name"] = row.get("security_name", "")
        per_stock[key]["trade_count"] += 1
        if side == "BUY":
            unit_cost = (amount + fee) / qty if qty else 0.0
            lots[key].append({"qty": qty, "unit_cost": unit_cost})
        elif side == "SELL":
            remaining = qty
            matched_cost = 0.0
            while remaining > 1e-9 and lots[key]:
                lot = lots[key][0]
                matched_qty = min(remaining, lot["qty"])
                matched_cost += matched_qty * lot["unit_cost"]
                lot["qty"] -= matched_qty
                remaining -= matched_qty
                if lot["qty"] <= 1e-9:
                    lots[key].pop(0)
            if remaining > 1e-9:
                unmatched_sells.append({"security": key, "quantity": round(remaining, 6), "source_row": row.get("source_row")})
            matched_qty = qty - remaining
            if matched_qty > 0:
                sell_revenue = (amount - fee) * (matched_qty / qty) if qty else 0.0
                pnl = sell_revenue - matched_cost
                per_stock[key]["realized_pnl"] += pnl
                per_stock[key]["realized_cost"] += matched_cost
                per_stock[key]["sell_revenue"] += sell_revenue
                monthly[month_of(row)] += pnl

    return per_stock, monthly, unmatched_sells


def summarize(trades):
    total_trades = len(trades)
    buy_trades = [r for r in trades if r.get("side") == "BUY"]
    sell_trades = [r for r in trades if r.get("side") == "SELL"]
    stocks = {stock_key(r) for r in trades}
    total_buy_amount = sum(abs(fnum(r.get("trade_amount"))) for r in buy_trades)
    total_sell_amount = sum(abs(fnum(r.get("trade_amount"))) for r in sell_trades)
    total_fees = sum(fnum(r.get("total_fee")) for r in trades)
    per_stock, monthly, unmatched_sells = fifo_realized(trades)
    pnl_values = [v["realized_pnl"] for v in per_stock.values() if abs(v["realized_pnl"]) > 1e-9]
    wins = [v for v in pnl_values if v > 0]
    losses = [v for v in pnl_values if v < 0]
    realized_pnl = sum(pnl_values)
    avg_profit = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    win_rate = len(wins) / len(pnl_values) if pnl_values else None
    profit_loss_ratio = (avg_profit / abs(avg_loss)) if wins and losses and avg_loss else None
    max_profit = max(per_stock.items(), key=lambda kv: kv[1]["realized_pnl"], default=(None, {"realized_pnl": 0.0}))
    max_loss = min(per_stock.items(), key=lambda kv: kv[1]["realized_pnl"], default=(None, {"realized_pnl": 0.0}))

    return {
        "summary": {
            "total_trades": total_trades,
            "buy_count": len(buy_trades),
            "sell_count": len(sell_trades),
            "stock_count": len(stocks),
            "total_buy_amount": round(total_buy_amount, 2),
            "total_sell_amount": round(total_sell_amount, 2),
            "total_fees": round(total_fees, 2),
            "realized_pnl": round(realized_pnl, 2),
            "win_rate": round(win_rate, 4) if win_rate is not None else "无法判断",
            "average_profit": round(avg_profit, 2) if wins else "无法判断",
            "average_loss": round(avg_loss, 2) if losses else "无法判断",
            "profit_loss_ratio": round(profit_loss_ratio, 4) if profit_loss_ratio is not None else "无法判断",
            "max_single_stock_profit": {"security": max_profit[0], "amount": round(max_profit[1]["realized_pnl"], 2)},
            "max_single_stock_loss": {"security": max_loss[0], "amount": round(max_loss[1]["realized_pnl"], 2)},
            "fee_ratio_to_turnover": round(total_fees / (total_buy_amount + total_sell_amount), 6) if (total_buy_amount + total_sell_amount) else "无法判断",
        },
        "per_stock_pnl": {
            key: {
                "security_name": value.get("security_name", ""),
                "realized_pnl": round(value["realized_pnl"], 2),
                "realized_cost": round(value["realized_cost"], 2),
                "sell_revenue": round(value["sell_revenue"], 2),
                "trade_count": value["trade_count"],
            }
            for key, value in sorted(per_stock.items())
        },
        "monthly_pnl": {key: round(value, 2) for key, value in sorted(monthly.items())},
        "data_warnings": {
            "unmatched_sells": unmatched_sells,
            "notes": ["若导入区间开始前已有持仓，FIFO 成本和已实现盈亏可能不完整。"] if unmatched_sells else [],
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Compute historical trade metrics from cleaned_trades.csv")
    parser.add_argument("cleaned_trades")
    parser.add_argument("-o", "--output", default="metrics.json")
    args = parser.parse_args()
    result = summarize(load_trades(args.cleaned_trades))
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
