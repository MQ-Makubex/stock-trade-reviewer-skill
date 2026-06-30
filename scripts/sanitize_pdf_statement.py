#!/usr/bin/env python3
import argparse
import csv
import json
import re
import sys
from pathlib import Path


FIELD_ALIASES = {
    "trade_date": ["发生日期", "成交日期", "交易日期"],
    "side": ["买卖类别", "买卖方向", "交易方向", "业务名称"],
    "stock_code": ["证券代码", "股票代码", "代码"],
    "stock_name": ["证券名称", "股票名称", "名称"],
    "quantity": ["成交数量", "成交股数", "数量"],
    "price": ["成交价格", "成交均价", "价格"],
    "net_amount": ["总发生金额", "发生金额", "资金发生额", "清算金额"],
    "commission": ["手续费", "佣金"],
    "stamp_tax": ["印花税"],
    "transfer_fee": ["过户费"],
    "cash_balance": ["资金余额", "余额", "可用余额"],
}

OUTPUT_FIELDS = [
    "trade_date",
    "side",
    "stock_code",
    "stock_name",
    "quantity",
    "price",
    "net_amount",
    "commission",
    "stamp_tax",
    "transfer_fee",
]

REQUIRED_FIELDS = ["trade_date", "side", "stock_code", "stock_name", "quantity", "price", "net_amount"]


def normalize_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\n", " ")).strip()


def normalize_header(value):
    return re.sub(r"[\s_\-:：/()（）]+", "", normalize_text(value).lower())


def normalize_side(value):
    text = normalize_text(value).upper()
    if "证券买入" in text or text in {"买入", "买", "BUY", "B"} or "BUY" in text:
        return "BUY"
    if "证券卖出" in text or text in {"卖出", "卖", "SELL", "S"} or "SELL" in text:
        return "SELL"
    return normalize_text(value)


def compact_number(value):
    text = normalize_text(value).replace(",", "").replace("￥", "").replace("¥", "")
    text = text.replace(" ", "")
    if re.fullmatch(r"\(([-+]?\d+(?:\.\d+)?)\)", text):
        return "-" + text.strip("()")
    return text


def build_header_mapping(header_row):
    mapping = {}
    normalized_cells = [normalize_header(cell) for cell in header_row]
    for canonical, aliases in FIELD_ALIASES.items():
        for index, cell in enumerate(normalized_cells):
            if not cell:
                continue
            if any(normalize_header(alias) == cell for alias in aliases):
                mapping[canonical] = index
                break
    return mapping


def is_header_like(row):
    mapping = build_header_mapping(row)
    return len(set(mapping) & set(REQUIRED_FIELDS)) >= 4


def extract_rows_from_tables(pdf_path):
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("缺少 pdfplumber。请在本地环境安装 pdfplumber 后重试，本脚本不会联网。") from exc

    sanitized_rows = []
    table_count = 0
    page_count = 0
    pages_with_tables = 0
    mappings_seen = []

    with pdfplumber.open(pdf_path) as pdf:
        page_count = len(pdf.pages)
        for page_number, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables() or []
            if tables:
                pages_with_tables += 1
            table_count += len(tables)
            for table_index, table in enumerate(tables, start=1):
                current_mapping = None
                for raw_row in table:
                    row = [normalize_text(cell) for cell in (raw_row or [])]
                    if not any(row):
                        continue
                    if is_header_like(row):
                        current_mapping = build_header_mapping(row)
                        mappings_seen.append({
                            "page": page_number,
                            "table": table_index,
                            "mapped_fields": sorted(current_mapping.keys()),
                        })
                        continue
                    if not current_mapping:
                        continue
                    extracted = row_to_record(row, current_mapping)
                    if extracted:
                        sanitized_rows.append(extracted)

    return sanitized_rows, {
        "page_count": page_count,
        "pages_with_tables": pages_with_tables,
        "table_count": table_count,
        "field_mappings_seen": mappings_seen,
    }


def cell_at(row, index):
    if index is None or index >= len(row):
        return ""
    return normalize_text(row[index])


def row_to_record(row, mapping):
    record = {}
    for field in OUTPUT_FIELDS + ["cash_balance"]:
        if field not in mapping:
            record[field] = ""
            continue
        value = cell_at(row, mapping[field])
        if field == "side":
            value = normalize_side(value)
        elif field in {"quantity", "price", "net_amount", "commission", "stamp_tax", "transfer_fee", "cash_balance"}:
            value = compact_number(value)
        record[field] = value

    if not looks_like_trade_row(record):
        return None
    return record


def looks_like_trade_row(record):
    if record.get("side") not in {"BUY", "SELL"}:
        return False
    if not (record.get("stock_code") or record.get("stock_name")):
        return False
    numeric_hits = sum(1 for field in ("quantity", "price", "net_amount") if re.search(r"\d", record.get(field, "")))
    return numeric_hits >= 2


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


def scan_sensitive_csv(csv_path):
    id_pattern = re.compile(r"(?<!\d)[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)")
    phone_pattern = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
    long_number_pattern = re.compile(r"(?<!\d)\d{8,24}(?!\d)")
    safe_numeric_fields = {
        "trade_date",
        "stock_code",
        "quantity",
        "price",
        "net_amount",
        "commission",
        "stamp_tax",
        "transfer_fee",
        "cash_balance",
    }
    findings = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for line_number, row in enumerate(reader, start=2):
            for field, value in row.items():
                value = value or ""
                if id_pattern.search(value):
                    findings.append({"line": line_number, "field": field, "type": "id_card"})
                if phone_pattern.search(value):
                    findings.append({"line": line_number, "field": field, "type": "phone"})
                if field not in safe_numeric_fields:
                    for match in long_number_pattern.findall(value):
                        if len(match) >= 13 and luhn_valid(match):
                            findings.append({"line": line_number, "field": field, "type": "bank_card_like"})
                        elif len(match) >= 8:
                            findings.append({"line": line_number, "field": field, "type": "long_account_like"})
    return findings


def write_csv(rows, output_path, keep_balance):
    fields = OUTPUT_FIELDS + (["cash_balance"] if keep_balance else [])
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_report(path, payload):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Extract and sanitize stock trade rows from a local PDF statement")
    parser.add_argument("pdf_file")
    parser.add_argument("-o", "--output", default="sanitized_trades.csv")
    parser.add_argument("--report", default="sanitize_pdf_report.json")
    parser.add_argument("--keep-balance", action="store_true", help="Keep cash_balance if present; default removes it")
    args = parser.parse_args()

    pdf_path = Path(args.pdf_file)
    if not pdf_path.exists():
        raise SystemExit(f"PDF 文件不存在: {pdf_path}")

    report = {
        "input_file": pdf_path.name,
        "output_file": args.output,
        "keep_balance": bool(args.keep_balance),
        "status": "started",
        "warnings": [],
        "privacy": [
            "未在终端打印 PDF 原文。",
            "只输出脱敏交易字段。",
            "默认删除资金余额；传入 --keep-balance 才保留。",
        ],
    }

    try:
        rows, extract_meta = extract_rows_from_tables(pdf_path)
        report.update(extract_meta)
    except Exception as exc:
        report["status"] = "error"
        report["error"] = str(exc)
        write_report(args.report, report)
        print(f"PDF 脱敏失败，详情见 {args.report}", file=sys.stderr)
        raise SystemExit(1)

    if not rows:
        report["status"] = "needs_ocr"
        report["warnings"].append("未从 PDF 提取到表格。该文件可能是扫描版 PDF，需要本地 OCR；本阶段不要联网。")
        write_report(args.report, report)
        print(f"未提取到表格，可能是扫描版 PDF，需要本地 OCR。详情见 {args.report}", file=sys.stderr)
        raise SystemExit(2)

    write_csv(rows, args.output, args.keep_balance)
    findings = scan_sensitive_csv(args.output)
    report["rows_extracted"] = len(rows)
    report["sensitive_scan_findings"] = findings

    if findings:
        report["status"] = "blocked_sensitive_data"
        report["warnings"].append("sanitized_trades.csv 二次扫描发现疑似敏感长数字，已阻止继续使用。")
        write_report(args.report, report)
        print(f"脱敏输出发现疑似敏感信息，已报错。详情见 {args.report}", file=sys.stderr)
        raise SystemExit(3)

    report["status"] = "ok"
    write_report(args.report, report)
    print(f"wrote {args.output}")
    print(f"wrote {args.report}")


if __name__ == "__main__":
    main()
