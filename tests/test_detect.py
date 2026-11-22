"""扫描引擎：义项判定、否定/转述排除、长短写法与歧义原因。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conceptwatch.corpus import Corpus  # noqa: E402
from conceptwatch.detect import scan_editions  # noqa: E402
from conceptwatch.models import SightingStatus, UsageType  # noqa: E402
from conceptwatch.registry import Registry  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"


class DetectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = Registry.from_file(DATA / "lexicon.json")
        cls.corpus = Corpus.from_file(DATA / "abstracts.json")
        cls.sightings = scan_editions(list(cls.corpus.editions), cls.registry)

    def _by_work(self, work_id):
        return [s for group in self.sightings.values() for s in group
                if s.work_id == work_id]

    def test_negated_and_reported_never_evidence(self):
        for s in self._by_work("W02"):
            self.assertEqual(s.status, SightingStatus.NEGATED)
            self.assertEqual(s.usage, UsageType.NEGATED)
        w10 = {s.start: s for s in self._by_work("W10")}
        # 第一处“织网”在“电价稿称……”转述小句里，不计证据
        first = sorted(w10.values(), key=lambda s: s.start)[0]
        self.assertEqual(first.status, SightingStatus.REPORTED)
        # 同篇后一句的自身使用仍是有效证据
        confirmed = [s for s in self._by_work("W10")
                     if s.status == SightingStatus.CONFIRMED]
        self.assertEqual(confirmed[0].sense_id, "C1-grid")

    def test_one_work_can_carry_two_senses(self):
        w04 = {s.sense_id for s in self._by_work("W04")
               if s.status == SightingStatus.CONFIRMED}
        self.assertEqual(w04, {"C1-gpu", "C1-grid"})

    def test_long_alias_is_strong_form_for_optical_sense(self):
        w08 = self._by_work("W08")
        self.assertEqual(len(w08), 1)
        self.assertEqual(w08[0].surface, "柔性织网")
        self.assertEqual(w08[0].sense_id, "C1-other")

    def test_ambiguity_records_candidates_and_reasons(self):
        w12 = self._by_work("W12")
        self.assertTrue(w12)
        for s in w12:
            self.assertEqual(s.status, SightingStatus.AMBIGUOUS)
            self.assertEqual(set(s.candidate_senses),
                             {"C1-gpu", "C1-grid"})
            self.assertTrue(s.reasons)

    def test_reported_clause_cannot_pollute_study_sense(self):
        # A8: grid 出现在 although 否定小句，本小句 mesh dispatch 仍定 gpu
        a8 = self.sightings["A8"]
        self.assertEqual(len(a8), 1)
        self.assertEqual(a8[0].status, SightingStatus.CONFIRMED)
        self.assertEqual(a8[0].sense_id, "C1-gpu")

    def test_retracted_edition_has_no_sightings(self):
        self.assertEqual(self.sightings["A10"], [])

    def test_correction_removes_old_claim(self):
        # A1 旧版声称跨域织网分配显存；A9 更正后该片段不再存在
        a9 = self.sightings["A9"]
        self.assertFalse(any(s.sense_id == "C1-gpu"
                             and s.status == SightingStatus.CONFIRMED
                             for s in a9))
        self.assertTrue(any(s.status == SightingStatus.REPORTED for s in a9))

    def test_sighting_ids_are_stable_across_runs(self):
        again = scan_editions(list(self.corpus.editions), self.registry)
        before = {s.sighting_id for g in self.sightings.values() for s in g}
        after = {s.sighting_id for g in again.values() for s in g}
        self.assertEqual(before, after)

    def test_registry_split_keeps_legacy_version_openable(self):
        lineage = self.registry.lineage("C2")
        self.assertEqual([v.registry_id for v in lineage], ["C1", "C2"])
        legacy = self.registry.get("C1")
        self.assertEqual([s.sense_id for s in legacy.senses], ["C1-any"])
        self.assertTrue(any(s.sense_id == "C1-gpu"
                            for s in self.registry.latest().senses))


if __name__ == "__main__":
    unittest.main()
