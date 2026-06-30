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
    "phone_number": ["手机号", "手机号码", "联系电话", "电话"],
    "fund_account": ["资金账号", "资金帐号", "资产账号", "资产帐号", "账户号", "账号"],
    "customer_id": ["客户号", "客户编号", "券商客户号"],
    "shareholder_account": ["股东账号", "股东帐号", "沪A账号", "深A账号"],
    "bank_card": ["银行卡", "银行账号", "银行帐号", "卡号"],
    "branch": ["营业部", "开户营业部"],
}

ADDRESS_HEADERS = ["地址", "联系地址", "通讯地址", "家庭地址", "开户地址", "营业部地址"]
BALANCE_HEADERS = ["资金余额", "可用余额", "余额", "资金结余", "cash_balance", "balance"]

STANDARD_TRADE_FIELDS = {
    "stock_name",
    "stock_code",
    "security_name",
    "security_code",
    "side",
    "trade_date",
    "price",
    "quantity",
    "amount",
    "trade_amount",
    "net_amount",
    "cash_amount",
    "commission",
    "stamp_tax",
    "transfer_fee",
    "other_fee",
    "证券名称",
    "证券代码",
    "股票名称",
    "股票代码",
    "买卖类别",
    "买卖方向",
    "交易方向",
    "发生日期",
    "成交日期",
    "成交价格",
    "成交数量",
    "成交金额",
    "总发生金额",
    "发生金额",
    "手续费",
    "印花税",
    "过户费",
    "其他费用",
}

REMARK_FIELDS = {"unknown", "raw", "remark", "备注", "摘要", "说明"}

SAFE_LONG_NUMBER_FIELDS = {
    "trade_date",
    "发生日期",
    "成交日期",
    "交易日期",
    "stock_code",
    "security_code",
    "证券代码",
    "股票代码",
    "代码",
    "quantity",
    "成交数量",
    "price",
    "成交价格",
    "net_amount",
    "cash_amount",
    "trade_amount",
    "amount",
    "总发生金额",
    "发生金额",
    "成交金额",
    "commission",
    "手续费",
    "stamp_tax",
    "印花税",
    "transfer_fee",
    "过户费",
    "other_fee",
    "其他费用",
}


def normalize(value):
    return re.sub(r"[\s_\-:：/()（）]+", "", str(value or "").strip().lower())


NORMALIZED_STANDARD_FIELDS = {normalize(value) for value in STANDARD_TRADE_FIELDS}
NORMALIZED_REMARK_FIELDS = {normalize(value) for value in REMARK_FIELDS}
NORMALIZED_SAFE_LONG_NUMBER_FIELDS = {normalize(value) for value in SAFE_LONG_NUMBER_FIELDS}


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


def finding(risk_type, severity, column, row_number, reason, action):
    return {
        "risk_type": risk_type,
        "severity": severity,
        "column": column,
        "row_number": row_number,
        "reason": reason,
        "action": action,
    }


def header_contains(header, keywords):
    normalized = normalize(header)
    return any(normalize(keyword) in normalized for keyword in keywords)


def is_standard_trade_field(header):
    return normalize(header) in NORMALIZED_STANDARD_FIELDS


def is_remark_field(header):
    return normalize(header) in NORMALIZED_REMARK_FIELDS


def looks_address_like(text):
    return bool(re.search(r"(省|市|区|县|街道|路|街|道|号|室|楼|单元)", str(text or "")))


def looks_detailed_address(text):
    text = str(text or "")
    region = re.search(r"(省|市|区|县)", text)
    street = re.search(r"(路|街|道|号|室|楼|单元)", text)
    # Require a combination, not just a single place name such as 上海机场 or 深圳市场.
    return bool(region and street)


def scan_headers(headers, strict_balance):
    errors = []
    warnings = []
    for header in headers:
        for risk_type, keywords in SENSITIVE_HEADER_KEYWORDS.items():
            if header_contains(header, keywords):
                errors.append(finding(
                    "sensitive_header",
                    "error",
                    header,
                    1,
                    f"表头包含高危敏感字段类型：{risk_type}",
                    "停止复盘，删除该字段后重新运行隐私检查。",
                ))
        if header_contains(header, ADDRESS_HEADERS):
            errors.append(finding(
                "address_like_text",
                "error",
                header,
                1,
                "表头本身是地址类字段。",
                "停止复盘，删除地址字段后重新运行隐私检查。",
            ))
        if any(normalize(keyword) == normalize(header) or normalize(keyword) in normalize(header) for keyword in BALANCE_HEADERS):
            target = errors if strict_balance else warnings
            target.append(finding(
                "cash_balance",
                "error" if strict_balance else "warning",
                header,
                1,
                "发现资金余额字段。",
                "严格模式下停止；默认模式允许继续，但建议删除余额字段。",
            ))
    return errors, warnings


def scan_cells(path, headers):
    id_pattern = re.compile(r"(?<!\d)[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)")
    phone_pattern = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
    long_number_pattern = re.compile(r"(?<!\d)\d{8,24}(?!\d)")
    errors = []
    warnings = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row_number, row in enumerate(reader, start=2):
            for header in headers:
                value = row.get(header, "") or ""
                normalized_header = normalize(header)

                if id_pattern.search(value):
                    errors.append(finding("id_card", "error", header, row_number, "单元格疑似包含身份证号。", "停止复盘，删除该值后重试。"))
                if phone_pattern.search(value):
                    errors.append(finding("phone_number", "error", header, row_number, "单元格疑似包含手机号。", "停止复盘，删除该值后重试。"))

                if normalized_header not in NORMALIZED_SAFE_LONG_NUMBER_FIELDS:
                    for match in long_number_pattern.findall(value):
                        if 16 <= len(match) <= 19 or (len(match) >= 13 and luhn_valid(match)):
                            errors.append(finding("bank_card", "error", header, row_number, "单元格疑似包含银行卡号。", "停止复盘，删除该值后重试。"))
                        elif len(match) >= 8:
                            errors.append(finding("account_like_long_number", "error", header, row_number, "单元格疑似包含账号类长数字。", "停止复盘，删除该值后重试。"))

                if looks_address_like(value):
                    if is_standard_trade_field(header):
                        warnings.append(finding(
                            "address_like_text",
                            "warning",
                            header,
                            row_number,
                            "标准交易字段中出现地名式文本，可能是证券名称或市场名称。",
                            "允许继续复盘；如该字段不是证券或交易字段，请人工复核。",
                        ))
                    elif is_remark_field(header) and looks_detailed_address(value):
                        errors.append(finding(
                            "address_like_text",
                            "error",
                            header,
                            row_number,
                            "备注/摘要/说明字段中出现明显完整地址组合。",
                            "停止复盘，删除地址内容后重试。",
                        ))
                    elif looks_detailed_address(value):
                        errors.append(finding(
                            "address_like_text",
                            "error",
                            header,
                            row_number,
                            "内容出现明显完整地址组合。",
                            "停止复盘，删除地址内容后重试。",
                        ))
                    else:
                        warnings.append(finding(
                            "address_like_text",
                            "warning",
                            header,
                            row_number,
                            "出现地名式文本，但不像完整地址。",
                            "允许继续复盘；建议人工确认是否为证券名称、市场名称或普通地名。",
                        ))
    return errors, warnings


def scan_csv(path, strict_balance=False):
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        try:
            headers = next(reader)
        except StopIteration:
            return {
                "status": "failed",
                "errors": [finding("empty_csv", "error", "file", 0, "CSV 没有表头或数据。", "停止复盘，提供有效 CSV。")],
                "warnings": [],
                "row_count": 0,
            }

    header_errors, header_warnings = scan_headers(headers, strict_balance)
    cell_errors, cell_warnings = scan_cells(path, headers)
    with open(path, newline="", encoding="utf-8") as fh:
        row_count = max(sum(1 for _ in csv.DictReader(fh)), 0)
    errors = header_errors + cell_errors
    warnings = header_warnings + cell_warnings
    return {
        "status": "failed" if errors else "ok",
        "errors": errors,
        "warnings": warnings,
        "row_count": row_count,
        "checked_file": Path(path).name,
        "strict_balance": strict_balance,
        "note": "报告只记录风险类型、位置、原因和处理动作，不记录原始单元格内容。",
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
        print(f"隐私检查失败，停止复盘。详情见 {args.output}", file=sys.stderr)
        raise SystemExit(1)
    if result["warnings"]:
        print(f"隐私检查通过，发现非阻断隐私警告，允许继续复盘。详情见 {args.output}")
    else:
        print(f"隐私检查通过，允许继续复盘。详情见 {args.output}")


if __name__ == "__main__":
    main()
