"""Unit tests for recipes.py. Run:  .venv/Scripts/python -m unittest discover -s tests -v"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recipes as R  # noqa: E402

TOY = [
    {"output": "Sword", "output_qty": 1, "facility": "Bench",
     "materials": [{"name": "Bar", "qty": "2"}, {"name": "Handle", "qty": "1"}], "skills": []},
    {"output": "Bar", "output_qty": 1, "facility": "Furnace", "materials": [{"name": "Ore", "qty": "3"}], "skills": []},
    {"output": "Bar", "output_qty": 1, "facility": "Furnace",
     "materials": [{"name": "Bar Salvage Pile", "qty": "9"}], "skills": []},
    {"output": "Handle", "output_qty": 2, "facility": "Bench", "materials": [{"name": "Logs", "qty": 1}], "skills": []},
    {"output": "Loop", "output_qty": 1, "facility": "X", "materials": [{"name": "Loop", "qty": 1}], "skills": []},
]
POWER = {"Sword": {"power": "4", "kind": "weapon"}, "Shield": {"power": "4", "kind": "armour"},
         "Bar": {"power": None, "kind": "armour"}}


class Toy(unittest.TestCase):
    def setUp(self):
        self.b = R.RecipeBook(TOY, POWER)

    def test_gear_filter_needs_power_and_recipe(self):
        self.assertEqual(self.b.gear(3, 6), [("Sword", 4, "weapon")])   # Shield has no recipe, Bar no power
        self.assertEqual(self.b.gear(5, 6), [])

    def test_primary_avoids_salvage(self):
        self.assertEqual(self.b.primary("Bar")["materials"][0]["name"], "Ore")

    def test_missing_full_chain(self):
        need, used = self.b.missing("Sword", 2)
        self.assertEqual(need, {"Ore": 12, "Logs": 1})   # 4 bars -> 12 ore; 2 handles = 1 craft of 2
        self.assertEqual(used, {})

    def test_missing_uses_inventory_at_every_level(self):
        need, used = self.b.missing("Sword", 1, {"Bar": 1, "Ore": 1, "Handle": 5})
        self.assertEqual(need, {"Ore": 2})                # 1 bar short -> 3 ore, have 1
        self.assertEqual(used, {"Bar": 1, "Ore": 1, "Handle": 1})

    def test_cycle_guard(self):
        need, _ = self.b.missing("Loop", 1)
        self.assertEqual(need, {"Loop": 1})

    def test_parse_inventory(self):
        have, unknown = self.b.parse_inventory("ore 5, 2 bar\nLogs x3; handle: 4, nonsense 9")
        self.assertEqual(have, {"Ore": 5, "Bar": 2, "Logs": 3, "Handle": 4})
        self.assertEqual(unknown, ["nonsense"])

    def test_node_for(self):
        res = {"Iron Ore Node", "Ash Tree", "Coal Node", "Limestone Rock"}
        self.assertEqual(R.node_for("Iron Ore", res), "Iron Ore Node")
        self.assertEqual(R.node_for("Ash Logs", res), "Ash Tree")
        self.assertEqual(R.node_for("Coal", res), "Coal Node")
        self.assertEqual(R.node_for("Limestone", res), "Limestone Rock")
        self.assertIsNone(R.node_for("Swamp Tar", res))


class RealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = R.RecipeBook.load()

    def test_iron_platebody(self):
        need, _ = self.b.missing("Iron Platebody", 1)
        self.assertEqual(need.get("Iron Ore"), 30)       # 10 Iron Bar x 3 ore (wiki: 3 Iron Ore -> 1 Iron Bar)

    def test_gear_3_to_6_nonempty(self):
        g = self.b.gear(3, 6)
        self.assertGreater(len(g), 100)
        self.assertTrue(all(3 <= p <= 6 for _, p, _ in g))
        self.assertIn("Iron Platebody", [n for n, _, _ in g])


if __name__ == "__main__":
    unittest.main()
