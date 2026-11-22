"""同口径比较：区间、去重、覆盖交集、不可比场景与抽核席位。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conceptwatch.audit import build_audit_plan, load_slots  # noqa: E402
from conceptwatch.compare import compare_months  # noqa: E402
from conceptwatch.corpus import Corpus  # noqa: E402
from conceptwatch.detect import scan_editions  # noqa: E402
from conceptwatch.registry import Registry  # noqa: E402
from conceptwatch.review import ReviewLedger  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"


class ComparisonFixture:
    def __init__(self):
        self.registry = Registry.from_file(DATA / "lexicon.json")
        self.corpus = Corpus.from_file(DATA / "abstracts.json",
                                       desk_path=DATA / "desk.json")
        self.sightings = scan_editions(list(self.corpus.editions),
                                       self.registry)
        self.ledger = ReviewLedger.from_file(DATA / "desk.json", self.registry)
        self.ledger.apply(self.sightings, self.corpus)
        self.result = compare_months("2026-08", "2026-09", self.corpus,
                                     self.registry, self.sightings)


class CompareTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = ComparisonFixture()
        cls.r = cls.fx.result

    def test_shared_coverage_and_denominators(self):
        self.assertTrue(self.r.comparable)
        self.assertEqual(set(self.r.shared_cells),
                         {("计算", "zh"), ("能源", "zh")})
        self.assertEqual(self.r.denominators,
                         {"2026-08": 5, "2026-09": 4})

    def test_sense_ranges_do_not_treat_uncertainty_as_zero(self):
        gpu = self.r.sense_trends["C1-gpu"]
        aug, sep = gpu.stats["2026-08"], gpu.stats["2026-09"]
        self.assertEqual((aug.low, aug.high), (1, 3))
        self.assertEqual((sep.low, sep.high), (2, 2))
        self.assertEqual((gpu.delta_low, gpu.delta_high), (1, -1))
        grid = self.r.sense_trends["C1-grid"]
        self.assertEqual((grid.stats["2026-08"].low,
                          grid.stats["2026-08"].high), (0, 2))
        self.assertEqual((grid.delta_low, grid.delta_high), (3, 1))

    def test_concept_union_deduplicates_work(self):
        # W04 同时含 gpu 与 grid，概念合计只算一次
        concept = self.r.concept_trend
        self.assertEqual((concept.stats["2026-09"].low,
                          concept.stats["2026-09"].high), (4, 4))
        self.assertEqual((concept.stats["2026-08"].low,
                          concept.stats["2026-08"].high), (1, 3))
        for st in concept.stats.values():
            self.assertEqual(len(st.low_works), len(set(st.low_works)))

    def test_language_versions_count_once(self):
        # W01 有中、英两个文种版本，分母与任何计数都只算一个 work
        aug = self.r.denominators["2026-08"]
        works = self.fx.corpus.valid_works(
            "2026-08", set(self.r.shared_cells))
        self.assertEqual(len(works), aug)
        self.assertEqual(works.count("W01"), 1)

    def test_pending_works_listed_separately(self):
        aug_gpu = self.r.sense_trends["C1-gpu"].stats["2026-08"]
        self.assertEqual(set(aug_gpu.pending_works), {"W11", "W12"})

    def test_out_of_scope_works_excluded(self):
        self.assertEqual(set(self.r.out_of_scope_works),
                         {"W03", "W07", "W08"})

    def test_empty_intersection_is_not_comparable(self):
        corpus = Corpus.from_file(DATA / "abstracts.json",
                                  desk_path=DATA / "desk.json")
        corpus.mark_complete("2026-10", "医学", "zh")
        result = compare_months("2026-08", "2026-10", corpus,
                                self.fx.registry, self.fx.sightings)
        self.assertFalse(result.comparable)
        self.assertTrue(result.reason)
        self.assertEqual(result.denominators, {"2026-08": 0, "2026-10": 0})


class AuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = ComparisonFixture()
        cls.slots = load_slots(DATA / "desk.json")
        cls.plan = build_audit_plan(
            cls.slots, cls.fx.sightings, cls.fx.corpus,
            excluded_works=cls.fx.result.out_of_scope_works)

    def test_every_change_has_seats_in_both_months_and_key_fields(self):
        by_sense = {}
        for a in self.plan.assignments:
            by_sense.setdefault(a.sense_id, set()).add((a.month, a.field))
        self.assertEqual(by_sense["C1-gpu"],
                         {("2026-08", "计算"), ("2026-09", "计算")})
        self.assertEqual(by_sense["C1-grid"],
                         {("2026-08", "能源"), ("2026-09", "能源")})

    def test_seats_point_back_to_snippets(self):
        filled = [a for a in self.plan.assignments if a.edition_id]
        for a in filled:
            self.assertIsNotNone(a.sighting_id)
            sighting = next(s for g in self.fx.sightings.values() for s in g
                            if s.sighting_id == a.sighting_id)
            self.assertTrue(sighting.snippet)

    def test_one_work_cannot_occupy_two_changes(self):
        works = [a.work_id for a in self.plan.assignments if a.work_id]
        self.assertEqual(len(works), len(set(works)))

    def test_missing_cell_is_explicitly_reported(self):
        self.assertTrue(any("C1-grid" in m and "2026-08" in m
                            for m in self.plan.missing_cells))
        vacant = [a for a in self.plan.assignments if a.edition_id is None]
        self.assertEqual(len(vacant), 1)

    def test_ambiguous_works_go_to_review_queue_not_seats(self):
        queue_works = {s.work_id for s in self.plan.review_queue}
        self.assertEqual(queue_works, {"W11", "W12"})
        seat_works = {a.work_id for a in self.plan.assignments}
        self.assertTrue(queue_works.isdisjoint(seat_works))

    def test_superseded_and_retracted_editions_cannot_fill_seats(self):
        used_editions = {a.edition_id for a in self.plan.assignments}
        self.assertNotIn("A1", used_editions)   # 已被 A9 更正
        self.assertNotIn("A4", used_editions)   # 已撤回

    def test_editorial_decisions_are_active_and_traced(self):
        states = {d.decision_id: d.state.value
                  for d in self.fx.ledger.decisions}
        self.assertEqual(states, {"D6": "active", "D7": "active"})
        # W05 原摘要存疑，经 D7 复核定为 gpu，决定挂在具体 sighting 上
        decided = [s for g in self.fx.sightings.values() for s in g
                   if s.decision_id == "D7"]
        self.assertTrue(decided)
        self.assertTrue(all(s.sense_id == "C1-gpu" for s in decided))
        decided6 = [s for g in self.fx.sightings.values() for s in g
                    if s.decision_id == "D6"]
        self.assertTrue(all(s.sense_id == "C1-grid" for s in decided6))


if __name__ == "__main__":
    unittest.main()
