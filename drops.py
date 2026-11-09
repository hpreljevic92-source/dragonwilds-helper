"""Drop sources (no UI): who/what drops an item, best chance first, and where those sources are on the map.

Data: data/drops.json + data/sources/*.json from fetch_data.py --drops (wiki, CC BY-NC-SA 3.0).
"""
import json
import re
from pathlib import Path

DATA = Path(__file__).with_name("data")


def chance(rarity):
    """'Always' -> 1.0, '1/6.7' -> 0.149, '25/100' -> 0.25; unknown text -> None."""
    if not rarity:
        return None
    s = str(rarity).strip().lower()
    if s == "always":
        return 1.0
    m = re.fullmatch(r"([\d.]+)\s*/\s*([\d.]+)", s)
    if m and float(m.group(2)):
        return min(1.0, float(m.group(1)) / float(m.group(2)))
    return None


class DropTable:
    def __init__(self, drops, source_points):
        self.by_item = {}
        for d in drops:
            if d.get("item") and d.get("source"):
                self.by_item.setdefault(d["item"], []).append(d)
        self.points = source_points  # {source name: [(x, y), ...]}

    @classmethod
    def load(cls, data_dir=DATA):
        drops = json.loads((data_dir / "drops.json").read_text(encoding="utf-8"))
        pts = {}
        for f in sorted((data_dir / "sources").glob("*.json")):
            raw = json.loads(f.read_text(encoding="utf-8"))
            pts[f.stem] = [(float(p["x"]), float(p["y"])) for p in raw if "x" in p and "y" in p]
        return cls(drops, pts)

    def has(self, item):
        return item in self.by_item

    def map_name(self, d):
        """Name of the map layer for a drop entry, or None. Tries the source, then its wiki page."""
        for n in (d["source"], d.get("page")):
            if n and self.points.get(n):
                return n
        return None

    def sources(self, item):
        """[{source, rarity, chance, qty, map}] best chance first; same source listed once (its best line)."""
        best = {}
        for d in self.by_item.get(item, []):
            c = chance(d.get("rarity"))
            row = {"source": d["source"], "rarity": d.get("rarity") or "?", "chance": c,
                   "qty": d.get("qty") or "?", "map": self.map_name(d)}
            old = best.get(d["source"])
            if old is None or (c or 0) > (old["chance"] or 0):
                best[d["source"]] = row
        # best chance first; among equal chances, ones you can find on the map first
        return sorted(best.values(), key=lambda r: (-(r["chance"] or 0), r["map"] is None, r["source"]))
