import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "privacy_guard.py"
spec = importlib.util.spec_from_file_location("privacy_guard", MODULE_PATH)
privacy_guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(privacy_guard)


class PrivacyGuardTests(unittest.TestCase):
    def scan_rows(self, headers, rows, strict_balance=False):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "input.csv"
            with path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(headers)
                writer.writerows(rows)
            return privacy_guard.scan_csv(path, strict_balance=strict_balance)

    def test_stock_names_with_place_words_do_not_fail(self):
        result = self.scan_rows(
            ["trade_date", "side", "stock_code", "stock_name", "quantity", "price", "net_amount"],
            [
                ["2025-01-01", "BUY", "600009", "上海机场", "100", "10.00", "-1000"],
                ["2025-01-02", "BUY", "601169", "北京银行", "100", "10.00", "-1000"],
                ["2025-01-03", "BUY", "600519", "贵州茅台", "100", "10.00", "-1000"],
                ["2025-01-04", "BUY", "601990", "南京证券", "100", "10.00", "-1000"],
                ["2025-01-05", "SELL", "SZMKT", "深圳市场", "100", "10.00", "1000"],
            ],
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["errors"], [])

    def test_address_headers_fail(self):
        for header in ("通讯地址", "家庭地址"):
            result = self.scan_rows(
                ["trade_date", "side", "stock_code", "stock_name", header],
                [["2025-01-01", "BUY", "DEMO", "虚构科技", "虚构市虚构路1号"]],
            )
            self.assertEqual(result["status"], "failed")
            self.assertTrue(any(item["risk_type"] == "address_like_text" and item["severity"] == "error" for item in result["errors"]))

    def test_detailed_address_in_remark_fails(self):
        result = self.scan_rows(
            ["trade_date", "side", "stock_code", "stock_name", "备注"],
            [["2025-01-01", "BUY", "DEMO", "虚构科技", "虚构省虚构市虚构路1号101室"]],
        )
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any(item["risk_type"] == "address_like_text" for item in result["errors"]))

    def test_high_risk_values_still_fail(self):
        fake_id_card = "110101" + "19900307" + "1234"
        fake_bank_card = "622202" + "123456" + "7890123"
        cases = [
            ("身份证", fake_id_card, "sensitive_header"),
            ("手机号", "13800138000", "sensitive_header"),
            ("备注", fake_bank_card, "bank_card"),
            ("资金账号", "1234567890", "sensitive_header"),
        ]
        for header, value, risk_type in cases:
            result = self.scan_rows(
                ["trade_date", "side", "stock_code", "stock_name", header],
                [["2025-01-01", "BUY", "DEMO", "虚构科技", value]],
            )
            self.assertEqual(result["status"], "failed")
            self.assertTrue(any(item["risk_type"] == risk_type for item in result["errors"]))


if __name__ == "__main__":
    unittest.main()
