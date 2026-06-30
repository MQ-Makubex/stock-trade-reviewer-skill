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


def parse_date(text):
    try:
        return datetime.strptime(str(text)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def load_trades(path):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    rows.sort(key=lambda r: (r.get("trade_date", ""), int(float(r.get("source_row") or 0))))
    return rows


def stock_key(row):
    return row.get("security_code") or row.get("security_name") or "UNKNOWN"


def classify_event(side, before_qty, after_qty):
    if side == "BUY":
        return "建仓" if before_qty <= 1e-9 and after_qty > 0 else "加仓"
    if side == "SELL":
        if after_qty <= 1e-9:
            return "清仓"
        return "减仓"
    return "无法判断"


def build_lifecycle(trades):
    state = defaultdict(lambda: {"lots": [], "events": [], "buy_amount": 0.0, "sell_revenue": 0.0, "realized_pnl": 0.0, "matched_days": [], "trade_count": 0})

    for row in trades:
        key = stock_key(row)
        item = state[key]
        item["security_name"] = row.get("security_name", "")
        item["trade_count"] += 1
        side = row.get("side")
        qty = fnum(row.get("quantity"))
        amount = abs(fnum(row.get("trade_amount")))
        fee = fnum(row.get("total_fee"))
        date = parse_date(row.get("trade_date"))
        before_qty = sum(lot["qty"] for lot in item["lots"])
        before_cost = sum(lot["qty"] * lot["unit_cost"] for lot in item["lots"])

        realized = 0.0
        matched_qty_total = 0.0
        if side == "BUY":
            unit_cost = (amount + fee) / qty if qty else 0.0
            item["lots"].append({"qty": qty, "unit_cost": unit_cost, "date": date.isoformat() if date else ""})
            item["buy_amount"] += amount + fee
        elif side == "SELL":
            remaining = qty
            matched_cost = 0.0
            while remaining > 1e-9 and item["lots"]:
                lot = item["lots"][0]
                matched_qty = min(remaining, lot["qty"])
                matched_cost += matched_qty * lot["unit_cost"]
                matched_qty_total += matched_qty
                lot_date = parse_date(lot["date"])
                if date and lot_date:
                    item["matched_days"].append((date - lot_date).days)
                lot["qty"] -= matched_qty
                remaining -= matched_qty
                if lot["qty"] <= 1e-9:
                    item["lots"].pop(0)
            if matched_qty_total > 0:
                revenue = (amount - fee) * (matched_qty_total / qty) if qty else 0.0
                realized = revenue - matched_cost
                item["sell_revenue"] += revenue
                item["realized_pnl"] += realized

        after_qty = sum(lot["qty"] for lot in item["lots"])
        after_cost = sum(lot["qty"] * lot["unit_cost"] for lot in item["lots"])
        item["events"].append({
            "date": row.get("trade_date", ""),
            "side": side,
            "event": classify_event(side, before_qty, after_qty),
            "quantity": qty,
            "price": fnum(row.get("price")),
            "amount": amount,
            "fee": fee,
            "position_before": round(before_qty, 6),
            "position_after": round(after_qty, 6),
            "avg_cost_after": round(after_cost / after_qty, 6) if after_qty else 0.0,
            "realized_pnl": round(realized, 2),
            "source_row": row.get("source_row", ""),
        })

    output = {}
    for key, item in state.items():
        open_qty = sum(lot["qty"] for lot in item["lots"])
        open_cost = sum(lot["qty"] * lot["unit_cost"] for lot in item["lots"])
        if item["matched_days"]:
            holding_days = round(sum(item["matched_days"]) / len(item["matched_days"]), 2)
            holding_note = "基于 FIFO 已卖出部分估算"
        elif open_qty > 0:
            holding_days = "无法判断"
            holding_note = "仍有未清仓持仓，且缺少完整卖出记录"
        else:
            holding_days = "无法判断"
            holding_note = "没有可匹配的买入和卖出日期"
        output[key] = {
            "security_name": item.get("security_name", ""),
            "average_cost_open_position": round(open_cost / open_qty, 6) if open_qty else 0.0,
            "open_quantity": round(open_qty, 6),
            "sell_revenue": round(item["sell_revenue"], 2),
            "realized_pnl": round(item["realized_pnl"], 2),
            "trade_count": item["trade_count"],
            "holding_days": holding_days,
            "holding_days_note": holding_note,
            "events": item["events"],
        }
    return output


def main():
    parser = argparse.ArgumentParser(description="Build per-stock trade lifecycle from cleaned_trades.csv")
    parser.add_argument("cleaned_trades")
    parser.add_argument("-o", "--output", default="trade_lifecycle.json")
    args = parser.parse_args()
    result = build_lifecycle(load_trades(args.cleaned_trades))
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
