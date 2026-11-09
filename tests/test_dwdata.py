"""Unit tests for the pure logic (no windows). Run:  .venv/Scripts/python -m unittest discover -s tests -v"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dwdata as dw  # noqa: E402


class Geometry(unittest.TestCase):
    def test_compass_directions(self):
        o = (0, 0)
        # game y grows southward, so north = negative y
        cases = {(0, -10): "N", (10, -10): "NE", (10, 0): "E", (10, 10): "SE",
                 (0, 10): "S", (-10, 10): "SW", (-10, 0): "W", (-10, -10): "NW"}
        for p, want in cases.items():
            self.assertEqual(dw.compass(dw.bearing_deg(o, p)), want, p)

    def test_compass_boundaries(self):
        self.assertEqual(dw.compass(22.4), "N")
        self.assertEqual(dw.compass(22.6), "NE")
        self.assertEqual(dw.compass(359.9), "N")

    def test_nearest_order_and_k(self):
        pts = [(100, 0), (5, 5), (50, 50), (-3, 0), (1000, 1000), (20, 0)]
        got = dw.nearest(pts, (0, 0), k=3)
        self.assertEqual([p for _, p in got], [(-3, 0), (5, 5), (20, 0)])
        self.assertAlmostEqual(got[0][0], 3.0)
        self.assertEqual(dw.nearest(pts, (0, 0), k=10).__len__(), len(pts))
        self.assertEqual(dw.nearest([], (0, 0)), [])

    def test_fmt_distance(self):
        self.assertEqual(dw.fmt_distance(8500), "85 m")
        self.assertEqual(dw.fmt_distance(250000), "2.5 km")

    def test_transform_roundtrip(self):
        t = dw.MapTransform(6144 / 420000 / 16 * 8, 11075, 117685)
        for g in [(0, 0), (18511.035, 108124.95), (-11075, -117685)]:
            back = t.to_game(*t.to_px(*g))
            self.assertAlmostEqual(back[0], g[0], places=6)
            self.assertAlmostEqual(back[1], g[1], places=6)
        self.assertEqual(t.to_px(-11075, -117685), (0.0, 0.0))  # wiki map's top-left bound


class RealData(unittest.TestCase):
    """Checks against the downloaded wiki data in ./data."""

    @classmethod
    def setUpClass(cls):
        cls.res = dw.load_resources()
        cls.t = dw.MapTransform.load()
        cls.size = json.loads((dw.DATA / "map_z3.json").read_text())["size"]

    def test_counts_and_hidden(self):
        self.assertEqual(len(self.res["Iron Ore Node"]), 199)
        for h in dw.HIDDEN:
            self.assertNotIn(h, self.res)
        self.assertEqual(len(self.res), 56 - len(dw.HIDDEN))

    def test_off_map_points_are_rare_and_filtered(self):
        total = sum(len(p) for p in self.res.values())
        off = [(n, p) for n, pts in self.res.items() for p in pts if not self.t.on_map(p)]
        self.assertLess(len(off) / total, 0.02, "more off-map points than expected - data changed?")
        self.assertTrue(all(self.t.on_map(p) for p in self.res["Iron Ore Node"]))

    def test_on_map_points_inside_image(self):
        w, h = self.size
        for name, pts in self.res.items():
            for p in pts:
                if self.t.on_map(p):
                    px, py = self.t.to_px(*p)
                    self.assertTrue(-50 <= px < w + 50 and -50 <= py < h + 50, f"{name} {p}")


if __name__ == "__main__":
    unittest.main()
