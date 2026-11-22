"""语料身份：重发沿用文献 ID、多文种同篇、更正不抹掉另一文种、撤回隐藏。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conceptwatch.corpus import Corpus  # noqa: E402
from conceptwatch.models import EditionStatus  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"


class CorpusIdentityTest(unittest.TestCase):
    def setUp(self):
        self.corpus = Corpus.from_file(DATA / "abstracts.json",
                                       desk_path=DATA / "desk.json")

    def test_resend_keeps_work_id_and_supersedes_old_edition(self):
        statuses = {
            e.edition_id: self.corpus.status_of(e)
            for e in self.corpus.editions_of("W01")
        }
        self.assertEqual(statuses["A1"], EditionStatus.SUPERSEDED)
        self.assertEqual(statuses["A9"], EditionStatus.CURRENT)
        # 英文版本不受中文更正影响，仍然有效
        self.assertEqual(statuses["A2"], EditionStatus.CURRENT)

    def test_retraction_hides_original_and_keeps_other_language(self):
        self.assertEqual(self.corpus.status_of(self.corpus.edition("A4")),
                         EditionStatus.RETRACTED)
        self.assertIsNone(self.corpus.visible_text("A4"))
        self.assertIsNone(self.corpus.visible_text("A10"))
        # W03 唯一文种被撤回，没有当前有效版本
        self.assertEqual(self.corpus.current_editions("W03"), ())
        # W01 的英文证据不受中文文件撤回/更正影响
        current = {e.edition_id for e in self.corpus.current_editions("W01")}
        self.assertEqual(current, {"A2", "A9"})

    def test_language_versions_are_one_work(self):
        self.assertEqual(
            {e.language for e in self.corpus.editions_of("W01")},
            {"zh", "en"})

    def test_receipt_intersection_is_comparison_coverage(self):
        shared = self.corpus.shared_complete_cells("2026-08", "2026-09")
        self.assertEqual(shared, {("计算", "zh"), ("能源", "zh")})
        self.assertIn(("计算", "en"),
                      self.corpus.excluded_cells("2026-08", shared))
        self.assertIn(("光学", "zh"),
                      self.corpus.excluded_cells("2026-09", shared))

    def test_denominator_counts_valid_works_only(self):
        shared = self.corpus.shared_complete_cells("2026-08", "2026-09")
        aug = self.corpus.valid_works("2026-08", shared)
        sep = self.corpus.valid_works("2026-09", shared)
        self.assertEqual(len(aug), 5)   # 与旧刊 covered=5 对齐
        self.assertEqual(len(sep), 4)
        self.assertNotIn("W03", aug)    # 撤回件不进分母
        self.assertNotIn("W07", sep)    # en 格九月未交齐
        self.assertNotIn("W08", sep)    # 光学格不在交集


if __name__ == "__main__":
    unittest.main()
