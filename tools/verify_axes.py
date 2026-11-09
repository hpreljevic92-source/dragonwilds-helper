"""Draw a resource's points on the map in both axis orders, to see which one lands on land.

  python tools/verify_axes.py "Iron Ore Node"   -> writes data/verify_A.png (x->px) and verify_B.png (y->px)
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

DATA = Path(__file__).resolve().parent.parent / "data"
name = sys.argv[1] if len(sys.argv) > 1 else "Iron Ore Node"
meta = json.loads((DATA / "map_z3.json").read_text())
pts = json.loads((DATA / "resources" / f"{name}.json").read_text(encoding="utf-8"))
s, ox, oy = meta["scale"], meta["offset_x"], meta["offset_y"]

for tag, swap in (("A", False), ("B", True)):
    img = Image.open(DATA / "map_z3.png").convert("RGB")
    d = ImageDraw.Draw(img)
    for p in pts:
        a, b = (p["y"], p["x"]) if swap else (p["x"], p["y"])
        px, py = (a + ox) * s, (b + oy) * s
        d.ellipse((px - 8, py - 8, px + 8, py + 8), fill=(255, 0, 0), outline=(255, 255, 255), width=2)
    img.resize((1024, 1024)).save(DATA / f"verify_{tag}.png")
    print(tag, "saved")
