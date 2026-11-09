"""Unit tests for drops.py. Run:  .venv/Scripts/python -m unittest discover -s tests -v"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import drops as D  # noqa: E402


class Logic(unittest.TestCase):
    def test_chance(self):
        self.assertEqual(D.chance("Always"), 1.0)
        self.assertAlmostEqual(D.chance("1/6.7"), 1 / 6.7)
        self.assertEqual(D.chance("25/100"), 0.25)
        self.assertIsNone(D.chance("Rare"))
        self.assertIsNone(D.chance(None))

    def test_sources_sorted_and_deduped(self):
        t = D.DropTable([
            {"item": "Hide", "source": "Wolf", "rarity": "1/10", "qty": "1"},
            {"item": "Hide", "source": "Wolf", "rarity": "1/2", "qty": "1"},       # better line, same source
            {"item": "Hide", "source": "Cow", "rarity": "Always", "qty": "1"},
            {"item": "Hide", "source": "Chest (X)", "rarity": "Always", "qty": "2"},
            {"item": "Hide", "source": "Ghost", "rarity": "Rare", "qty": "1"},
        ], {"Cow": [(0, 0)], "Wolf": [(1, 1)]})
        got = [(r["source"], r["map"]) for r in t.sources("Hide")]
        self.assertEqual(got, [("Cow", "Cow"), ("Chest (X)", None), ("Wolf", "Wolf"), ("Ghost", None)])
        self.assertEqual(t.sources("Nothing"), [])


class RealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = D.DropTable.load()

    def test_animal_hide_has_mappable_always_source(self):
        s = self.t.sources("Animal Hide")
        self.assertTrue(any(r["chance"] == 1.0 and r["map"] for r in s), s[:5])
        self.assertIn("Deer", [r["source"] for r in s])


if __name__ == "__main__":
    unittest.main()
