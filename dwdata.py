"""Pure data/geometry helpers for the Dragonwilds helper (no UI, no Win32) so they can be unit-tested."""
import heapq
import json
import math
from pathlib import Path

DATA = Path(__file__).with_name("data")

# Pages that matched the resource filter but aren't gatherable resources.
HIDDEN = {"Exploding Plant Trap", "Nodestone", "Sapphire Emblem", "Plant Salvage"}

# ASSUMPTION (unverified): Dragonwilds is Unreal Engine, where 1 unit = 1 cm.
UNITS_PER_METER = 100

COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def load_resources(data_dir=DATA):
    """{resource name: [(x, y), ...]} in game units, from the cached wiki JSON."""
    out = {}
    for f in sorted((data_dir / "resources").glob("*.json")):
        if f.stem in HIDDEN:
            continue
        pts = json.loads(f.read_text(encoding="utf-8"))
        out[f.stem] = [(float(p["x"]), float(p["y"])) for p in pts if "x" in p and "y" in p]
    return out


class MapTransform:
    """Game units <-> map-image pixels. Formula from the wiki's MediaWiki:Gadget-maps.js.

    Verified visually: game x -> image horizontal, game y -> image vertical (y grows downward = south).
    """

    def __init__(self, scale, offset_x, offset_y, size=None):
        self.scale, self.offset_x, self.offset_y, self.size = scale, offset_x, offset_y, size

    @classmethod
    def load(cls, data_dir=DATA, zoom=3):
        m = json.loads((data_dir / f"map_z{zoom}.json").read_text())
        return cls(m["scale"], m["offset_x"], m["offset_y"], tuple(m["size"]))

    def on_map(self, p, margin_px=50):
        """False for points far outside the map image. ~0.8% of wiki points are like that
        (clusters near x=-460000, probably vault/cave interiors stored in their own coordinate space)."""
        px, py = self.to_px(*p)
        w, h = self.size
        return -margin_px <= px < w + margin_px and -margin_px <= py < h + margin_px

    def to_px(self, x, y):
        return (x + self.offset_x) * self.scale, (y + self.offset_y) * self.scale

    def to_game(self, px, py):
        return px / self.scale - self.offset_x, py / self.scale - self.offset_y


def bearing_deg(frm, to):
    """Compass bearing from frm to to, 0 = north (map up), 90 = east. Game y grows southward."""
    dx, dy = to[0] - frm[0], to[1] - frm[1]
    return math.degrees(math.atan2(dx, -dy)) % 360


def compass(deg):
    return COMPASS[int((deg + 22.5) // 45) % 8]


def nearest(points, here, k=5):
    """[(distance_in_units, (x, y)), ...] for the k points closest to here."""
    return heapq.nsmallest(k, ((math.dist(here, p), p) for p in points))


def fmt_distance(units):
    m = units / UNITS_PER_METER
    return f"{m:.0f} m" if m < 1000 else f"{m / 1000:.1f} km"
