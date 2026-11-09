"""One-time, cached download of public wiki data for the Dragonwilds helper.

Source: dragonwilds.runescape.wiki (CC BY-NC-SA 3.0). Nothing here touches the game.

  python fetch_data.py --list           # only list resource data pages (2-3 small API calls)
  python fetch_data.py --resources      # download resource coordinate JSONs
  python fetch_data.py --map 3          # download + stitch map tiles at zoom 3 (144 tiles, ~10 MB)

Everything goes into ./data. Existing files are skipped (re-run with --force to refresh).
"""
import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

API = "https://dragonwilds.runescape.wiki/api.php"
TILES = "https://maps.runescape.wiki/dw/tiles/{z}/{x}_{y}.png"
UA = "dragonwilds-helper/0.1 (personal non-commercial overlay; python-urllib)"
DELAY = 1.0  # seconds between requests: be polite to the wiki

DATA = Path(__file__).with_name("data")
RES_DIR = DATA / "resources"

# Which Module:Map/<name>.json pages count as "resources" (gatherable nodes).
RESOURCE_RE = re.compile(r"(Node|Tree|Deposit|Vein|Rock|Bush|Plant|Cactus|Mushroom|Flax|Cabbage|Weed|"
                         r"Harralander|Sap|Bark|Root|Fishing)", re.I)

# Map transform copied from MediaWiki:Gadget-maps.js (game units -> pixels at zoom 0).
MULT = 6144 / 420000 / 16
OFFSET_X = 11075
OFFSET_Y = 100800 + 16885
TILE = 256


def get(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    time.sleep(DELAY)
    return body


def api(**params):
    params.update(format="json", formatversion="2")
    return json.loads(get(API, params))


def list_map_pages():
    """All Module:Map/*.json titles (namespace 828 = Module)."""
    titles, cont = [], {}
    while True:
        d = api(action="query", list="allpages", apnamespace=828, apprefix="Map/", aplimit=500, **cont)
        titles += [p["title"] for p in d["query"]["allpages"] if p["title"].endswith(".json")]
        if "continue" not in d:
            return titles
        cont = {"apcontinue": d["continue"]["apcontinue"]}


def resource_name(title):
    return title.removeprefix("Module:Map/").removesuffix(".json")


def fetch_resources(titles, force):
    RES_DIR.mkdir(parents=True, exist_ok=True)
    todo = [t for t in titles if force or not (RES_DIR / f"{resource_name(t)}.json").exists()]
    print(f"{len(titles)} resource pages, {len(todo)} to download")
    for i in range(0, len(todo), 50):  # API allows 50 titles per request
        batch = todo[i:i + 50]
        d = api(action="query", prop="revisions", rvprop="content", rvslots="main", titles="|".join(batch))
        for page in d["query"]["pages"]:
            if page.get("missing"):
                print("  missing:", page["title"])
                continue
            raw = page["revisions"][0]["slots"]["main"]["content"]
            try:
                points = json.loads(raw)
            except json.JSONDecodeError:
                print("  bad json:", page["title"])
                continue
            name = resource_name(page["title"])
            (RES_DIR / f"{name}.json").write_text(json.dumps(points, indent=1), encoding="utf-8")
            print(f"  {name}: {len(points)} points")


def fetch_map(z, force):
    from PIL import Image  # only needed here

    out = DATA / f"map_z{z}.png"
    if out.exists() and not force:
        print(out, "already exists")
        return
    n = int(6144 / 16 * 2 ** z / TILE + 0.999)  # tiles per side: z2 -> 6, z3 -> 12
    img = Image.new("RGB", (n * TILE, n * TILE), (20, 20, 20))
    for ty in range(n):
        for tx in range(n):
            try:
                tile = Image.open(BytesIO(get(TILES.format(z=z, x=tx, y=ty))))
                img.paste(tile, (tx * TILE, ty * TILE))
            except Exception as e:  # missing edge tiles are fine
                print(f"  tile {tx}_{ty}: {e}")
        print(f"  row {ty + 1}/{n}")
    DATA.mkdir(exist_ok=True)
    img.save(out)
    meta = {"zoom": z, "size": img.size, "scale": MULT * 2 ** z, "offset_x": OFFSET_X, "offset_y": OFFSET_Y,
            "note": "pixel = (game_coord + offset) * scale; axis order still to be verified"}
    (DATA / f"map_z{z}.json").write_text(json.dumps(meta, indent=1))
    print("saved", out, img.size)


def bucket(query):
    d = json.loads(get(API, {"action": "bucket", "format": "json", "query": query}))
    if "error" in d:
        raise RuntimeError(f"bucket query failed: {d['error']}")
    return d["bucket"]


def fetch_recipes(force):
    """All recipes + armour/weapon power levels (3 requests). -> data/recipes.json, data/power.json"""
    out_r, out_p = DATA / "recipes.json", DATA / "power.json"
    if out_r.exists() and out_p.exists() and not force:
        print("recipes already downloaded")
        return
    DATA.mkdir(exist_ok=True)
    rows = bucket("bucket('recipe').select('page_name','json').limit(5000).run()")
    recipes = []
    for r in rows:
        try:
            j = json.loads(r["json"])
        except (KeyError, json.JSONDecodeError):
            continue
        out = j.get("output") or {}
        recipes.append({
            "page": r.get("page_name"),
            "output": out.get("name"),
            "output_qty": out.get("quantity", 1),
            "facility": j.get("facility"),
            "materials": [{"name": m.get("name"), "qty": m.get("quantity", 1)} for m in j.get("materials", [])],
            "skills": [{"name": s.get("name"), "xp": s.get("experience")} for s in j.get("skills", [])],
        })
    out_r.write_text(json.dumps(recipes, indent=0), encoding="utf-8")
    print(f"  {len(recipes)} recipes")

    power = {}
    for r in bucket("bucket('infobox_armour').select('page_name','item_power').limit(5000).run()"):
        power[r["page_name"]] = {"power": r.get("item_power"), "kind": "armour"}
    for r in bucket("bucket('infobox_weapon').select('page_name','weapon_power').limit(5000).run()"):
        power[r["page_name"]] = {"power": r.get("weapon_power"), "kind": "weapon"}
    out_p.write_text(json.dumps(power, indent=0), encoding="utf-8")
    print(f"  {len(power)} items with a power level")


def fetch_drops(force):
    """Drop table (who drops what) + map positions for the drop sources that have wiki map data.
    -> data/drops.json, data/sources/<source>.json"""
    out = DATA / "drops.json"
    if out.exists() and not force:
        print("drops already downloaded")
    else:
        DATA.mkdir(exist_ok=True)
        drops = []
        for r in bucket("bucket('dropsline').select('page_name','item_name','json').limit(10000).run()"):
            try:
                j = json.loads(r["json"])
            except (KeyError, json.JSONDecodeError):
                continue
            drops.append({"item": j.get("Dropped item") or r.get("item_name"),
                          "source": j.get("Dropped from") or r.get("page_name"),
                          "page": r.get("page_name"), "rarity": j.get("Rarity"),
                          "qty": j.get("Drop Quantity")})
        out.write_text(json.dumps(drops, indent=0), encoding="utf-8")
        print(f"  {len(drops)} drop entries")

    drops = json.loads(out.read_text(encoding="utf-8"))
    wanted = {d["source"] for d in drops} | {d["page"] for d in drops}
    have_map = {resource_name(t): t for t in list_map_pages()}
    titles = [have_map[s] for s in sorted(wanted) if s in have_map]
    src_dir = DATA / "sources"
    src_dir.mkdir(exist_ok=True)
    todo = [t for t in titles if force or not (src_dir / f"{resource_name(t)}.json").exists()]
    print(f"  {len(titles)} of {len(wanted)} sources have map data, {len(todo)} to download")
    for i in range(0, len(todo), 50):
        d = api(action="query", prop="revisions", rvprop="content", rvslots="main", titles="|".join(todo[i:i + 50]))
        for page in d["query"]["pages"]:
            if page.get("missing"):
                continue
            try:
                pts = json.loads(page["revisions"][0]["slots"]["main"]["content"])
            except json.JSONDecodeError:
                continue
            (src_dir / f"{resource_name(page['title'])}.json").write_text(json.dumps(pts, indent=1), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--resources", action="store_true")
    ap.add_argument("--map", type=int, choices=[2, 3])
    ap.add_argument("--recipes", action="store_true", help="recipes + armour/weapon power levels")
    ap.add_argument("--drops", action="store_true", help="drop table + drop-source map positions")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.recipes:
        fetch_recipes(a.force)
    if a.drops:
        fetch_drops(a.force)
    if not (a.list or a.resources or a.map is not None or a.recipes or a.drops):
        ap.print_help()
        return

    if a.list or a.resources:
        titles = [t for t in list_map_pages() if RESOURCE_RE.search(resource_name(t))]
        DATA.mkdir(exist_ok=True)
        (DATA / "resource_index.json").write_text(json.dumps([resource_name(t) for t in titles], indent=1))
        print("\n".join(resource_name(t) for t in titles))
        if a.resources:
            fetch_resources(titles, a.force)
    if a.map is not None:
        fetch_map(a.map, a.force)


if __name__ == "__main__":
    sys.exit(main())
