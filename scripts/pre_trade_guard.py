#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def load_json(path, default):
    if not path or not Path(path).exists():
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_questions(playbooks, behavior):
    questions = []
    for item in playbooks.get("playbooks", {}).get("应避免", []):
        questions.append(f"这笔交易是否触发历史应避免模式：{item.get('trigger_condition', '无法判断')}？最大风险是否已写清？")
    for item in playbooks.get("playbooks", {}).get("待验证", []):
        questions.append(f"这笔交易是否只是重复待验证模式：{item.get('trigger_condition', '无法判断')}？退出方式是否与历史证据一致？")
    for name, flag in behavior.get("behavior_flags", {}).items():
        if flag.get("status") == "触发":
            questions.append(f"下单前确认：今天是否正在重复“{name}”？如果是，先写出停止条件。")
    if not questions:
        questions.append("历史样本不足，无法生成针对性反问；请先写清入场理由、退出方式和最大风险。")
    return questions[:12]


def main():
    parser = argparse.ArgumentParser(description="基于历史模式生成买入前风控反问")
    parser.add_argument("--playbooks", default="local_state/playbooks.json")
    parser.add_argument("--behavior", default="behavior_flags.json")
    parser.add_argument("-o", "--output", default="pre_trade_guard.json")
    args = parser.parse_args()

    payload = {
        "scope": "仅做买入前风控训练，不荐股、不预测涨跌、不输出买卖建议。",
        "questions": build_questions(load_json(args.playbooks, {}), load_json(args.behavior, {})),
    }
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
