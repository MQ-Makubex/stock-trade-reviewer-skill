import unittest

from scripts.article_digest import narrative_checks
from scripts.generate_coach_report import build_report
from scripts.playbook_manager import empty_store, update_playbooks


class CoachModuleTests(unittest.TestCase):
    def test_article_digest_narrative_pollution_checks(self):
        checks = narrative_checks("低估不用怕，业绩数据需要核验，但不要踏空追涨。", {"article_influenced": True})
        self.assertEqual(set(checks), {
            "reinforces_position_bias",
            "induces_chasing",
            "has_verifiable_facts",
            "is_emotional_comfort",
            "affected_today_trade",
        })
        self.assertTrue(checks["reinforces_position_bias"]["flag"])
        self.assertTrue(checks["induces_chasing"]["flag"])
        self.assertTrue(checks["has_verifiable_facts"]["flag"])
        self.assertTrue(checks["affected_today_trade"]["flag"])

    def test_playbook_requires_three_dates_before_copyable(self):
        metrics = {
            "per_stock_pnl": {
                "DEMOA": {"security_name": "虚构科技", "realized_pnl": 120.0}
            }
        }
        behavior = {"behavior_flags": {}}
        store = empty_store()
        for day in ["2026-01-01", "2026-01-02"]:
            update_playbooks(store, metrics, {}, behavior, {"trade_date": day})
        self.assertEqual(store["playbooks"]["可复制"], [])
        self.assertEqual(store["playbooks"]["待验证"][0]["evidence_count"], 2)
        update_playbooks(store, metrics, {}, behavior, {"trade_date": "2026-01-03"})
        self.assertEqual(store["playbooks"]["待验证"], [])
        self.assertEqual(store["playbooks"]["可复制"][0]["validation_status"], "可复制")

    def test_loss_or_risk_goes_to_avoid(self):
        metrics = {
            "per_stock_pnl": {
                "DEMOB": {"security_name": "虚构制造", "realized_pnl": -500.0}
            }
        }
        behavior = {"behavior_flags": {"单票亏损过大": {"status": "触发", "severity": "高", "interpretation": "风险集中"}}}
        store = update_playbooks(empty_store(), metrics, {}, behavior, {"trade_date": "2026-01-01"})
        avoid = store["playbooks"]["应避免"]
        self.assertGreaterEqual(len(avoid), 2)
        for item in avoid:
            self.assertIn("trigger_condition", item)
            self.assertIn("entry_reason_type", item)
            self.assertIn("exit_method", item)
            self.assertIn("max_risk", item)
            self.assertIn("evidence_dates", item)
            self.assertIn("validation_status", item)

    def test_coach_report_has_qualitative_sentence(self):
        report = build_report(
            {"summary": {"total_trades": 1, "buy_count": 1, "sell_count": 0, "realized_pnl": -10.0, "total_fees": 1.0}, "per_stock_pnl": {}},
            {},
            {"behavior_flags": {}},
            {"trade_date": "2026-01-01", "trading_idea": "虚构想法"},
            {"narrative_pollution_checks": {}},
            {"playbooks": {"可复制": [], "待验证": [], "应避免": []}},
            {"questions": []},
        )
        self.assertIn("today_qualitative", report)
        self.assertTrue(report["today_qualitative"].endswith("。"))


if __name__ == "__main__":
    unittest.main()
