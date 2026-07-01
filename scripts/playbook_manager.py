#!/usr/bin/env python3
import argparse
import json
from datetime import date
from pathlib import Path


CATEGORIES = ["可复制", "待验证", "应避免"]


def load_json(path, default):
    if not path or not Path(path).exists():
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def empty_store():
    return {"version": 1, "updated_at": "", "playbooks": {name: [] for name in CATEGORIES}}


def security_label(item):
    return f"{item.get('security_code') or item.get('security') or ''} {item.get('security_name') or ''}".strip() or "无法判断"


def pattern_key(trigger, entry_reason, exit_style, max_risk):
    return "|".join([trigger, entry_reason, exit_style, max_risk])


def infer_exit_style(item):
    pnl = float(item.get("realized_pnl") or item.get("pnl") or 0)
    days = item.get("holding_days")
    if pnl > 0 and days is not None and float(days) <= 5:
        return "短持兑现"
    if pnl < 0 and days is not None and float(days) >= 20:
        return "亏损拖延"
    if pnl < 0:
        return "亏损退出"
    return "计划内退出待验证"


def max_risk_label(item):
    pnl = float(item.get("realized_pnl") or item.get("pnl") or 0)
    if pnl < -3000:
        return "高"
    if pnl < 0:
        return "中"
    return "低"


def existing_by_key(store):
    index = {}
    for category in CATEGORIES:
        for entry in store.get("playbooks", {}).get(category, []):
            index[entry.get("pattern_key")] = (category, entry)
    return index


def candidate_from_stock(code, item, evidence_date):
    pnl = float(item.get("realized_pnl") or item.get("pnl") or 0)
    trigger = "盈利后按计划兑现" if pnl > 0 else "亏损或风险失控"
    entry_reason = "用户交易想法/成交结果复盘"
    exit_style = infer_exit_style(item)
    max_risk = max_risk_label(item)
    status = "待验证" if pnl > 0 and max_risk != "高" else "应避免"
    if status == "应避免":
        trigger = "亏损扩大、拖延退出或风险失控"
    return {
        "pattern_key": pattern_key(trigger, entry_reason, exit_style, max_risk),
        "name": f"{trigger}：{security_label({'security_code': code, **item})}",
        "trigger_condition": trigger,
        "entry_reason_type": entry_reason,
        "exit_method": exit_style,
        "max_risk": max_risk,
        "evidence_dates": [evidence_date],
        "evidence_count": 1,
        "validation_status": status,
        "notes": "由历史成交、当日想法和行为诊断生成；不构成买卖建议。",
    }


def risk_candidates(behavior, evidence_date):
    rows = []
    for name, item in behavior.get("behavior_flags", {}).items():
        if item.get("status") != "触发":
            continue
        severity = item.get("severity", "")
        if severity not in {"中", "高"}:
            continue
        rows.append({
            "pattern_key": pattern_key(name, "风险行为诊断", "纪律复盘", severity),
            "name": f"应避免：{name}",
            "trigger_condition": name,
            "entry_reason_type": "风险行为诊断",
            "exit_method": "纪律复盘",
            "max_risk": severity,
            "evidence_dates": [evidence_date],
            "evidence_count": 1,
            "validation_status": "应避免",
            "notes": item.get("interpretation") or "风险行为触发。",
        })
    return rows


def merge_entry(store, candidate):
    index = existing_by_key(store)
    current = index.get(candidate["pattern_key"])
    if current:
        category, entry = current
        for day in candidate["evidence_dates"]:
            if day not in entry["evidence_dates"]:
                entry["evidence_dates"].append(day)
        entry["evidence_count"] = len(entry["evidence_dates"])
        if category != "应避免" and candidate["validation_status"] == "应避免":
            store["playbooks"][category].remove(entry)
            entry["validation_status"] = "应避免"
            store["playbooks"]["应避免"].append(entry)
        elif category == "待验证" and entry["evidence_count"] >= 3:
            store["playbooks"]["待验证"].remove(entry)
            entry["validation_status"] = "可复制"
            store["playbooks"]["可复制"].append(entry)
        return
    store["playbooks"][candidate["validation_status"]].append(candidate)


def update_playbooks(store, metrics, lifecycle, behavior, journal):
    evidence_date = journal.get("trade_date") or date.today().isoformat()
    per_stock = metrics.get("per_stock_pnl", {})
    for code, item in per_stock.items():
        merge_entry(store, candidate_from_stock(code, item, evidence_date))
    for candidate in risk_candidates(behavior, evidence_date):
        merge_entry(store, candidate)
    store["updated_at"] = evidence_date
    return store


def main():
    parser = argparse.ArgumentParser(description="保守更新长期交易 playbook")
    parser.add_argument("--metrics", default="metrics.json")
    parser.add_argument("--lifecycle", default="trade_lifecycle.json")
    parser.add_argument("--behavior", default="behavior_flags.json")
    parser.add_argument("--journal", default="daily_journal.json")
    parser.add_argument("--state", default="local_state/playbooks.json")
    parser.add_argument("-o", "--output", default="")
    args = parser.parse_args()

    store = load_json(args.state, empty_store())
    updated = update_playbooks(
        store,
        load_json(args.metrics, {}),
        load_json(args.lifecycle, {}),
        load_json(args.behavior, {}),
        load_json(args.journal, {}),
    )
    output = args.output or args.state
    save_json(output, updated)
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
