#!/usr/bin/env python3
import argparse
import json
from datetime import date
from pathlib import Path


def load_json(path):
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_journal(args):
    payload = load_json(args.input_json)
    return {
        "trade_date": payload.get("trade_date") or args.trade_date or date.today().isoformat(),
        "trading_idea": payload.get("trading_idea") or args.trading_idea or "",
        "trade_intent": payload.get("trade_intent") or args.trade_intent or "",
        "mood": payload.get("mood") or args.mood or "",
        "plan": payload.get("plan") or args.plan or "",
        "review_note": payload.get("review_note") or args.review_note or "",
        "article_influenced": bool(payload.get("article_influenced", args.article_influenced)),
        "discipline_tags": payload.get("discipline_tags") or args.discipline_tags or [],
        "privacy_note": "仅保存用户输入的交易想法摘要，不保存原始 PDF、截图或未脱敏交易文件。",
    }


def main():
    parser = argparse.ArgumentParser(description="保存每日交易想法到 daily_journal.json")
    parser.add_argument("--input-json", default="")
    parser.add_argument("--trade-date", default="")
    parser.add_argument("--trading-idea", default="")
    parser.add_argument("--trade-intent", default="")
    parser.add_argument("--mood", default="")
    parser.add_argument("--plan", default="")
    parser.add_argument("--review-note", default="")
    parser.add_argument("--article-influenced", action="store_true")
    parser.add_argument("--discipline-tags", nargs="*", default=[])
    parser.add_argument("-o", "--output", default="daily_journal.json")
    args = parser.parse_args()

    journal = build_journal(args)
    Path(args.output).write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
