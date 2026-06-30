#!/usr/bin/env python3
import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime


def fnum(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_trades(path):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    rows.sort(key=lambda r: (r.get("trade_date", ""), int(float(r.get("source_row") or 0))))
    return rows


def stock_key(row):
    return row.get("security_code") or row.get("security_name") or "UNKNOWN"


def parse_date(text):
    try:
        return datetime.strptime(str(text)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def flag(status, severity, evidence, interpretation, limitation=None):
    return {
        "status": status,
        "severity": severity,
        "evidence": evidence,
        "interpretation": interpretation,
        "limitation": limitation or "",
    }


def detect_small_win_big_loss(metrics):
    summary = metrics["summary"]
    avg_profit = summary.get("average_profit")
    avg_loss = summary.get("average_loss")
    max_loss = summary.get("max_single_stock_loss", {})
    if isinstance(avg_profit, str) or isinstance(avg_loss, str):
        return flag("无法判断", "低", ["缺少同时包含盈利和亏损的已实现单票样本"], "无法判断小赚大亏。")
    ratio = abs(avg_loss) / avg_profit if avg_profit else 0
    status = ratio >= 1.5 or abs(max_loss.get("amount", 0)) >= avg_profit * 2
    return flag(
        "触发" if status else "未触发",
        "高" if ratio >= 2 else "中" if status else "低",
        [f"平均盈利 {avg_profit}", f"平均亏损 {avg_loss}", f"亏损/盈利倍数 {ratio:.2f}"],
        "亏损单的破坏力显著大于盈利单。" if status else "当前样本未显示明显小赚大亏。",
    )


def detect_frequency(trades):
    by_month = Counter(r.get("trade_date", "")[:7] for r in trades if r.get("trade_date"))
    by_day = Counter(r.get("trade_date", "") for r in trades if r.get("trade_date"))
    max_month = max(by_month.values(), default=0)
    max_day = max(by_day.values(), default=0)
    status = max_month >= 20 or max_day >= 4 or (len(trades) >= 12 and len(by_month) <= 1)
    return flag(
        "触发" if status else "未触发",
        "高" if max_month >= 30 or max_day >= 6 else "中" if status else "低",
        [f"最高单月交易 {max_month} 笔", f"最高单日交易 {max_day} 笔"],
        "交易频率偏高，可能让费用和情绪噪音放大。" if status else "当前样本未显示明显频繁交易。",
    )


def detect_repeat_stock(trades):
    counts = Counter(stock_key(r) for r in trades)
    repeated = {k: v for k, v in counts.items() if v >= 6}
    return flag(
        "触发" if repeated else "未触发",
        "中" if repeated else "低",
        [f"{k}: {v} 笔" for k, v in sorted(repeated.items(), key=lambda kv: -kv[1])[:5]],
        "同一股票反复买卖，需检查是否有事前计划。" if repeated else "未发现单票过度反复交易。",
    )


def detect_single_stock_loss(metrics):
    per_stock = metrics.get("per_stock_pnl", {})
    losses = sorted([(k, v["realized_pnl"]) for k, v in per_stock.items() if v["realized_pnl"] < 0], key=lambda x: x[1])
    total_loss = abs(sum(v for _, v in losses))
    large = [(k, v) for k, v in losses if total_loss and abs(v) / total_loss >= 0.4]
    return flag(
        "触发" if large else "未触发",
        "高" if large else "低",
        [f"{k}: {v:.2f}, 占总亏损 {abs(v) / total_loss:.1%}" for k, v in large] if total_loss else ["没有已实现亏损样本"],
        "少数股票贡献了主要亏损，风险集中。" if large else "未发现单票亏损过度集中。",
    )


def detect_fee_drag(metrics):
    s = metrics["summary"]
    fee_ratio = s.get("fee_ratio_to_turnover")
    realized = s.get("realized_pnl", 0)
    total_fees = s.get("total_fees", 0)
    high = isinstance(fee_ratio, float) and (fee_ratio >= 0.003 or (realized > 0 and total_fees / realized >= 0.2) or (realized <= 0 and total_fees > 0))
    return flag(
        "触发" if high else "未触发",
        "中" if high else "低",
        [f"总费用 {total_fees}", f"费用/成交额 {fee_ratio if isinstance(fee_ratio, str) else format(fee_ratio, '.4%')}", f"已实现盈亏 {realized}"],
        "费用对结果有明显侵蚀，尤其在高频或低胜率时会放大。" if high else "费用占比未显示明显异常。",
    )


def detect_holding_patterns(lifecycle):
    profit_days = []
    loss_days = []
    for key, item in lifecycle.items():
        days = item.get("holding_days")
        pnl = item.get("realized_pnl", 0)
        if isinstance(days, (int, float)):
            if pnl > 0:
                profit_days.append((key, days, pnl))
            elif pnl < 0:
                loss_days.append((key, days, pnl))
    quick_profit = [x for x in profit_days if x[1] <= 3]
    long_loss = [x for x in loss_days if x[1] >= 20]
    take_profit = flag(
        "触发" if quick_profit else "未触发",
        "中" if quick_profit else "低",
        [f"{k}: 盈利 {pnl:.2f}, 持仓 {days} 天" for k, days, pnl in quick_profit[:5]],
        "盈利交易持仓很短，需检查是否过早兑现。" if quick_profit else "未发现明显盈利拿不住。",
        "只使用成交日期，缺少盘中和未成交价格。",
    )
    hold_loss = flag(
        "触发" if long_loss else "未触发",
        "高" if long_loss else "低",
        [f"{k}: 亏损 {pnl:.2f}, 持仓 {days} 天" for k, days, pnl in long_loss[:5]],
        "亏损交易持有较久，需检查止损与复盘纪律。" if long_loss else "未发现明显亏损持有过久。",
        "仅基于已卖出部分估算。",
    )
    return take_profit, hold_loss


def detect_emotional_trading(trades):
    by_day = defaultdict(list)
    for row in trades:
        by_day[row.get("trade_date", "")].append(row)
    evidence = []
    for date, rows in by_day.items():
        if len(rows) >= 4:
            evidence.append(f"{date}: {len(rows)} 笔交易")
        by_stock = defaultdict(set)
        for row in rows:
            by_stock[stock_key(row)].add(row.get("side"))
        for key, sides in by_stock.items():
            if {"BUY", "SELL"} <= sides:
                evidence.append(f"{date} {key}: 同日买卖")
    return flag(
        "触发" if evidence else "未触发",
        "中" if evidence else "低",
        evidence[:8],
        "存在短时间集中交易或同日反向交易，疑似情绪交易。" if evidence else "未发现明显情绪交易迹象。",
        "没有委托时间和下单原因，只能标记为疑似。",
    )


def detect_chasing_high(trades):
    by_stock = defaultdict(list)
    for row in trades:
        by_stock[stock_key(row)].append(row)
    evidence = []
    for key, rows in by_stock.items():
        last_sell_price = None
        for row in rows:
            price = fnum(row.get("price"))
            if row.get("side") == "SELL":
                last_sell_price = price
            elif row.get("side") == "BUY" and last_sell_price and price >= last_sell_price * 1.05:
                evidence.append(f"{key}: 买入价 {price:.2f} 高于此前卖出价 {last_sell_price:.2f} 超过 5%")
    return flag(
        "触发" if evidence else "未触发",
        "中" if evidence else "低",
        evidence[:8],
        "成交记录显示疑似卖飞后更高价追回。" if evidence else "未发现可由成交价支持的追高迹象。",
        "缺少市场行情，无法判断买入时是否处于市场高位。",
    )


def detect_averaging_down(trades, metrics):
    by_stock = defaultdict(list)
    for row in trades:
        by_stock[stock_key(row)].append(row)
    evidence = []
    for key, rows in by_stock.items():
        buy_prices = []
        for row in rows:
            if row.get("side") == "BUY":
                price = fnum(row.get("price"))
                if buy_prices and price < (sum(buy_prices) / len(buy_prices)) * 0.97:
                    pnl = metrics.get("per_stock_pnl", {}).get(key, {}).get("realized_pnl", 0)
                    if pnl <= 0:
                        evidence.append(f"{key}: 下跌后继续买入，最终已实现盈亏 {pnl:.2f}")
                buy_prices.append(price)
    return flag(
        "触发" if evidence else "未触发",
        "中" if evidence else "低",
        evidence[:8],
        "存在越跌越买且结果未改善的迹象，疑似补仓摊薄幻觉。" if evidence else "未发现可由成交价支持的补仓摊薄幻觉。",
        "缺少交易理由和未实现盈亏，只能用成交价格与结果近似判断。",
    )


def detect(trades, metrics, lifecycle):
    take_profit, hold_loss = detect_holding_patterns(lifecycle)
    flags = {
        "小赚大亏": detect_small_win_big_loss(metrics),
        "频繁交易": detect_frequency(trades),
        "同一股票反复买卖": detect_repeat_stock(trades),
        "单票亏损过大": detect_single_stock_loss(metrics),
        "手续费消耗过高": detect_fee_drag(metrics),
        "盈利拿不住": take_profit,
        "亏损持有过久": hold_loss,
        "疑似情绪交易": detect_emotional_trading(trades),
        "疑似追高": detect_chasing_high(trades),
        "疑似补仓摊薄幻觉": detect_averaging_down(trades, metrics),
    }
    return {"behavior_flags": flags}


def main():
    parser = argparse.ArgumentParser(description="Detect behavior patterns from trade history")
    parser.add_argument("cleaned_trades")
    parser.add_argument("metrics_json")
    parser.add_argument("lifecycle_json")
    parser.add_argument("-o", "--output", default="behavior_flags.json")
    args = parser.parse_args()
    result = detect(load_trades(args.cleaned_trades), load_json(args.metrics_json), load_json(args.lifecycle_json))
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
