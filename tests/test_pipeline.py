"""端到端：工作稿、出刊快照、旧刊撤回留档与复核后重新协调。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conceptwatch.audit import build_audit_plan, load_slots, recoordinate  # noqa: E402
from conceptwatch.compare import compare_months  # noqa: E402
from conceptwatch.models import DecisionState, SightingStatus  # noqa: E402
from conceptwatch.pipeline import render_report, run_pipeline  # noqa: E402
from conceptwatch.publish import explain_historical, freeze_issue, load_historical_bulletins  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"


class PipelineEndToEndTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_pipeline(DATA, "2026-08", "2026-09")

    def test_report_renders_key_figures(self):
        report = render_report(self.result)
        self.assertIn("分母（交齐格内有效文献）：{'2026-08': 5, '2026-09': 4}",
                      report)
        self.assertIn("变化区间：+1 ~ -1 篇", report)   # gpu
        self.assertIn("变化区间：+3 ~ +1 篇", report)   # grid
        self.assertIn("席位空缺", report)
        self.assertIn("送人审的存疑片段", report)

    def test_issue_snapshot_freezes_current_registry(self):
        issue = self.result.issue
        self.assertEqual(issue.registry_id, "C2")
        self.assertEqual(issue.denominators,
                         {"2026-08": 5, "2026-09": 4})
        self.assertTrue(issue.audit)
        self.assertTrue(issue.missing_cells)

    def test_historical_bulletin_explains_retraction_without_text(self):
        bulletins = load_historical_bulletins(DATA / "desk.json")
        explained = [explain_historical(b, self.result.corpus,
                                        self.result.registry)
                     for b in bulletins]
        self.assertEqual(len(explained), 1)
        h = explained[0]
        self.assertEqual(h["legacy_registry"]["id"], "C1")  # 旧口径仍可打开
        entries = {e["edition_id"]: e for e in h["evidence_entries"]}
        self.assertEqual(entries["A4"]["current_status"], "retracted")
        self.assertFalse(entries["A4"]["text_visible"])
        self.assertIn("不可用", entries["A4"]["evidence_note"])
        self.assertEqual(entries["A1"]["current_status"], "superseded")
        # 快照保留当时计数
        self.assertEqual(h["published_ratios"], {"works": 2, "covered": 5})
        # 任何路径都取不到撤回原文
        self.assertIsNone(self.result.corpus.visible_text("A4"))

    def test_recoordination_after_editorial_review(self):
        # 模拟编辑复核 W11（A14）定为 gpu：趋势与席位都要重算
        sightings = self.result.sightings
        a14 = next(s for s in sightings["A14"])
        self.assertEqual(a14.status, SightingStatus.AMBIGUOUS)
        a14_new = a14.with_decision("TEST-D", "C1-gpu")
        sightings["A14"][0] = a14_new

        comparison = compare_months("2026-08", "2026-09",
                                    self.result.corpus, self.result.registry,
                                    sightings)
        gpu_aug = comparison.sense_trends["C1-gpu"].stats["2026-08"]
        self.assertEqual(gpu_aug.low, 2)       # W09 + W11
        self.assertEqual(gpu_aug.high, 3)      # W12 仍存疑
        grid_aug = comparison.sense_trends["C1-grid"].stats["2026-08"]
        self.assertEqual(grid_aug.high, 1)     # W11 已定 gpu，grid 上限只剩 W12
        self.assertEqual(set(grid_aug.high_works), {"W12"})

        slots = load_slots(DATA / "desk.json")
        plan = recoordinate(slots, sightings, self.result.corpus,
                            excluded_works=comparison.out_of_scope_works)
        # grid 八月席位仍空缺（W11 已被 gpu 决定，不能占 grid 席位）
        vacant = [a for a in plan.assignments if a.edition_id is None]
        self.assertTrue(any(a.sense_id == "C1-grid" and a.month == "2026-08"
                            for a in vacant))

    def test_stale_decision_when_edition_retracted(self):
        # 构造一个指向撤回件的决定，验证留档但不套用
        from conceptwatch.models import EditorialDecision
        from conceptwatch.review import ReviewLedger
        ledger = ReviewLedger()
        ledger.add(EditorialDecision(
            decision_id="X1", work_id="W03", edition_id="A4",
            sense_id="C1-grid", note="测试"))
        report = ledger.apply(self.result.sightings, self.result.corpus)
        self.assertEqual(report.stale[0][0].state, DecisionState.STALE)
        self.assertIn("撤回", report.stale[0][1])


if __name__ == "__main__":
    unittest.main()
