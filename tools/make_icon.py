"""Make helper.ico: a round crop of the world map with a red map pin. Run once."""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
src = Image.open(ROOT / "data" / "map_z3.png").convert("RGBA")
# crop around the western continent (Highlands/Brynmoor area), square
art = src.crop((150, 1100, 1350, 2300)).resize((256, 256), Image.Resampling.LANCZOS)

mask = Image.new("L", (256, 256), 0)
ImageDraw.Draw(mask).ellipse((4, 4, 252, 252), fill=255)
icon = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
icon.paste(art, (0, 0), mask)

d = ImageDraw.Draw(icon)
d.ellipse((4, 4, 252, 252), outline=(255, 210, 63, 255), width=10)          # gold ring
d.polygon([(128, 200), (92, 120), (164, 120)], fill=(230, 40, 40, 255))    # pin tip
d.ellipse((86, 58, 170, 142), fill=(230, 40, 40, 255), outline=(255, 255, 255, 255), width=6)
d.ellipse((114, 86, 142, 114), fill=(255, 255, 255, 255))

icon.save(ROOT / "helper.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
icon.save(ROOT / "data" / "icon_preview.png")
print("saved", ROOT / "helper.ico")
