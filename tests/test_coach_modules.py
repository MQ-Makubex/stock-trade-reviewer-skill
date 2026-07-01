import unittest

from scripts.article_digest import narrative_checks
from scripts.generate_coach_report import build_report, to_xueqiu_markdown
from scripts.macro_lens_digest import article_from_text, aggregate_lenses
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

    def test_macro_lens_enters_reasoning_not_trade_advice(self):
        report = build_report(
            {"summary": {"total_trades": 2, "buy_count": 1, "sell_count": 1, "realized_pnl": 20.0, "total_fees": 1.0}, "per_stock_pnl": {}},
            {},
            {"behavior_flags": {}},
            {"trade_date": "2026-01-02", "trading_idea": "大盘看不懂，科技和防守风格切换不确定，5日线试错。", "plan": "破10日线止损。"},
            {"narrative_pollution_checks": {}, "viewpoints": ["虚构观点"]},
            {"playbooks": {"可复制": [], "待验证": [], "应避免": []}},
            {"questions": []},
            {"source": {"name": "虚构宏观博主", "updated_at": "2026-01-02"}, "macro_lenses": [{"lens": "市场风格", "observation": "风格切换需要市场确认", "risk_tags": ["可验证事实不足"]}]},
        )
        self.assertIn("market_context", report)
        self.assertIn("coach_reasoning", report)
        self.assertIn("macro_lens", report)
        joined = "\n".join(report["tomorrow_discipline"])
        self.assertIn("条件计划", joined)
        self.assertNotIn("建议买入", joined)
        self.assertNotIn("建议卖出", joined)

    def test_xueqiu_post_uses_units_and_conditions(self):
        report = build_report(
            {
                "summary": {"total_trades": 1, "buy_count": 1, "sell_count": 0, "realized_pnl": 0.0, "total_fees": 1.0},
                "per_stock_pnl": {"301421": {"security_name": "虚构光电", "trade_count": 1, "sell_revenue": 0.0, "realized_cost": 59600.0, "realized_pnl": 0.0}},
            },
            {},
            {"behavior_flags": {}},
            {"trade_date": "2026-01-02", "trading_idea": "5日线试错，破10日线止损。", "plan": "只用一单位。"},
            {"narrative_pollution_checks": {}, "viewpoints": []},
            {"playbooks": {"可复制": [], "待验证": [], "应避免": []}},
            {"questions": []},
            {},
        )
        post = to_xueqiu_markdown(report)
        self.assertIn("301421 虚构光电", post)
        self.assertIn("约1单位", post)
        self.assertIn("条件计划", post)
        self.assertNotIn("59,600", post)

    def test_macro_digest_extracts_lenses_without_full_text(self):
        article = article_from_text("https://example.test/a", "虚构文章", "政策周期影响风险偏好。长期主义不能替代止损纪律。")
        lenses = aggregate_lenses([article])
        self.assertTrue(lenses)
        self.assertTrue(any("宏观" in item["lens"] or "政策" in item["lens"] for item in lenses))


if __name__ == "__main__":
    unittest.main()
