"""检查交换资料的标识、文本和跨表引用。"""

import json
from pathlib import Path
import unittest


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class SourceDataTest(unittest.TestCase):
    def setUp(self):
        self.tables = {}
        for path in sorted(DATA_DIR.glob("*.json")):
            rows = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsInstance(rows, list)
            self.assertTrue(rows, path.name)
            by_id = {}
            for row in rows:
                identifier = row["id"]
                self.assertIsInstance(identifier, str, path.name)
                self.assertNotIn(identifier, by_id, path.name)
                if "text" in row:
                    self.assertIsInstance(row["text"], str, path.name)
                by_id[identifier] = row
            self.tables[path.stem] = by_id

    def test_exchange_tables_present(self):
        self.assertEqual(set(self.tables), {'abstracts', 'desk', 'lexicon'})

    def test_related_source_records(self):
        data = self.tables
        works = {(row["work"], row["language"], row["serial"]) for row in data["abstracts"].values()}
        self.assertIn(("W01", "en", 1), works)
        self.assertIn(("W01", "zh", 2), works)
        self.assertTrue(data["abstracts"]["A10"]["retract"])
        self.assertEqual(data["abstracts"]["A10"]["work"], data["abstracts"]["A4"]["work"])
        self.assertIn(["计算", "en"], data["desk"]["D1"]["complete"])
        self.assertNotIn(["计算", "en"], data["desk"]["D2"]["complete"])
        self.assertTrue(set(data["desk"]["D5"]["editions"]) <= data["abstracts"].keys())
