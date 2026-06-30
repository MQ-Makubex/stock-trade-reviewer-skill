#!/usr/bin/env python3
import argparse
import csv
import json
import re
import sys
from pathlib import Path


SENSITIVE_HEADER_KEYWORDS = {
    "name": ["姓名", "客户姓名", "户名", "真实姓名"],
    "id_card": ["身份证", "证件号码", "证件号", "身份证号"],
    "phone": ["手机号", "手机号码", "联系电话", "电话"],
    "fund_account": ["资金账号", "资金帐号", "资产账号", "资产帐号", "账户号", "账号"],
    "client_id": ["客户号", "客户编号", "券商客户号"],
    "shareholder_account": ["股东账号", "股东帐号", "沪A账号", "深A账号"],
    "bank_card": ["银行卡", "银行账号", "银行帐号", "卡号"],
    "branch": ["营业部", "开户营业部"],
    "address": ["地址", "联系地址", "通讯地址"],
}

BALANCE_HEADERS = ["资金余额", "可用余额", "余额", "资金结余", "cash_balance", "balance"]

SAFE_LONG_NUMBER_FIELDS = {
    "trade_date",
    "发生日期",
    "成交日期",
    "交易日期",
    "stock_code",
    "证券代码",
    "股票代码",
    "代码",
    "quantity",
    "成交数量",
    "price",
    "成交价格",
    "net_amount",
    "总发生金额",
    "发生金额",
    "commission",
    "手续费",
    "stamp_tax",
    "印花税",
    "transfer_fee",
    "过户费",
}


def normalize(value):
    return re.sub(r"[\s_\-:：/()（）]+", "", str(value or "").strip().lower())


def luhn_valid(number):
    digits = [int(ch) for ch in number if ch.isdigit()]
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def finding(location, kind, severity):
    return {"location": location, "type": kind, "severity": severity}


def scan_headers(headers, strict_balance):
    errors = []
    warnings = []
    normalized_headers = {header: normalize(header) for header in headers}
    for header, normalized in normalized_headers.items():
        for kind, keywords in SENSITIVE_HEADER_KEYWORDS.items():
            if any(normalize(keyword) in normalized for keyword in keywords):
                errors.append(finding(f"header:{header}", kind, "error"))
        if any(normalize(keyword) == normalized or normalize(keyword) in normalized for keyword in BALANCE_HEADERS):
            target = errors if strict_balance else warnings
            target.append(finding(f"header:{header}", "cash_balance", "error" if strict_balance else "warning"))
    return errors, warnings


def scan_cells(path, headers):
    id_pattern = re.compile(r"(?<!\d)[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)")
    phone_pattern = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
    long_number_pattern = re.compile(r"(?<!\d)\d{8,24}(?!\d)")
    address_pattern = re.compile(r"(省|市|区|县|街道|路|号楼|单元|室)")
    errors = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row_number, row in enumerate(reader, start=2):
            for header in headers:
                value = row.get(header, "") or ""
                location = f"row:{row_number},field:{header}"
                if id_pattern.search(value):
                    errors.append(finding(location, "id_card", "error"))
                if phone_pattern.search(value):
                    errors.append(finding(location, "phone", "error"))
                if address_pattern.search(value) and normalize(header) not in {normalize(x) for x in SAFE_LONG_NUMBER_FIELDS}:
                    errors.append(finding(location, "address_like_text", "error"))
                if normalize(header) not in {normalize(x) for x in SAFE_LONG_NUMBER_FIELDS}:
                    for match in long_number_pattern.findall(value):
                        if len(match) >= 13 and luhn_valid(match):
                            errors.append(finding(location, "bank_card_like", "error"))
                        elif len(match) >= 8:
                            errors.append(finding(location, "account_like_long_number", "error"))
    return errors


def scan_csv(path, strict_balance=False):
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        try:
            headers = next(reader)
        except StopIteration:
            return {
                "status": "failed",
                "errors": [finding("file", "empty_csv", "error")],
                "warnings": [],
                "row_count": 0,
            }

    header_errors, warnings = scan_headers(headers, strict_balance)
    cell_errors = scan_cells(path, headers)
    with open(path, newline="", encoding="utf-8") as fh:
        row_count = max(sum(1 for _ in csv.DictReader(fh)), 0)
    errors = header_errors + cell_errors
    return {
        "status": "failed" if errors else "ok",
        "errors": errors,
        "warnings": warnings,
        "row_count": row_count,
        "checked_file": Path(path).name,
        "strict_balance": strict_balance,
        "note": "报告只记录风险类型和位置，不记录原始单元格内容。",
    }


def main():
    parser = argparse.ArgumentParser(description="本地检查脱敏交易 CSV 是否含敏感信息")
    parser.add_argument("input_csv", help="通常为 sanitized_trades.csv")
    parser.add_argument("-o", "--output", default="privacy_guard_report.json")
    parser.add_argument("--strict-balance", action="store_true", help="发现资金余额字段时直接失败")
    args = parser.parse_args()

    result = scan_csv(args.input_csv, strict_balance=args.strict_balance)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    if result["status"] != "ok":
        print(f"隐私检查失败，详情见 {args.output}", file=sys.stderr)
        raise SystemExit(1)
    if result["warnings"]:
        print(f"隐私检查通过，但存在警告，详情见 {args.output}")
    else:
        print(f"隐私检查通过，详情见 {args.output}")


if __name__ == "__main__":
    main()
