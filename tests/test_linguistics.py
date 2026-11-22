"""语言习惯层：长短边界、否定/转述区分、线索作用域。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conceptwatch.linguistics import (  # noqa: E402
    classify_usage,
    iter_matches,
    iter_sentences,
    split_clauses,
)


class MatchingTest(unittest.TestCase):
    def test_long_form_swallows_short_form_zh(self):
        text = "柔性织网与跨域织网都是织网"
        matches = iter_matches(text,
                               ["织网", "柔性织网", "跨域织网"], "zh")
        surfaces = [(m.start, m.surface) for m in matches]
        self.assertEqual(surfaces,
                         [(0, "柔性织网"), (5, "跨域织网"), (11, "织网")])
        # 柔性织网内部不会再切出一个织网
        self.assertTrue(all(not (m.start == 0 and m.surface == "织网")
                            for m in matches))

    def test_english_word_boundary_case_insensitive(self):
        text = "Our cluster uses MESH dispatch for GPUs; meshdx is unrelated."
        matches = iter_matches(text, ["mesh dispatch"], "en")
        self.assertEqual([m.surface for m in matches], ["MESH dispatch"])

    def test_english_phrase_kept_whole(self):
        self.assertEqual(
            [m.surface for m in
             iter_matches("mesh dispatch", ["mesh dispatch", "mesh"], "en")],
            ["mesh dispatch"])


class UsageTest(unittest.TestCase):
    def _owner(self, text, language="zh"):
        sentences = iter_sentences(text, language)
        clauses = split_clauses(sentences[0], language)
        return clauses, classify_usage(
            clauses[0], clauses[1:], language)

    def test_contrast_negation_consideration(self):
        clauses, (usage, cues) = self._owner("曾考虑织网，但没有分配储能。")
        self.assertEqual(usage, "negated")
        self.assertIn("contrast_negated", cues)

    def test_contrast_keeps_study_when_affirmative(self):
        text = "Our cluster uses mesh dispatch, although the grid study does not."
        sentences = iter_sentences(text, "en")
        clauses = split_clauses(sentences[0], "en")
        owner = next(c for c in clauses if "mesh dispatch" in c.text)
        usage, _ = classify_usage(owner, [c for c in clauses if c is not owner],
                                  "en")
        self.assertEqual(usage, "study")

    def test_reported_clause(self):
        _, (usage, cues) = self._owner("简报提到电站织网的实验。")
        self.assertEqual(usage, "reported")
        self.assertIn("reported", cues)

    def test_local_negation(self):
        _, (usage, _) = self._owner("本文的织网并未用于储能。")
        self.assertEqual(usage, "negated")


if __name__ == "__main__":
    unittest.main()
