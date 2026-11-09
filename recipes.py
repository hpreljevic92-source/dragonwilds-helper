"""Recipe logic (no UI): power-level filter, ingredient chains, "what am I missing".

Data: data/recipes.json + data/power.json from fetch_data.py --recipes (wiki, CC BY-NC-SA 3.0).
"""
import json
import math
import re
from pathlib import Path

DATA = Path(__file__).with_name("data")


def _qty(v):
    """Wiki quantities are strings like '4' (sometimes ints). Take the first number; default 1."""
    m = re.search(r"\d+(\.\d+)?", str(v))
    return float(m.group()) if m else 1.0


def _int_or_none(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


class RecipeBook:
    def __init__(self, recipes, power):
        self.by_output = {}
        for r in recipes:
            if not r.get("output"):
                continue
            r = dict(r, output_qty=_qty(r.get("output_qty", 1)),
                     materials=[{"name": m["name"], "qty": _qty(m["qty"])} for m in r["materials"] if m.get("name")])
            self.by_output.setdefault(r["output"], []).append(r)
        self.power = {k: (_int_or_none(v.get("power")), v.get("kind")) for k, v in power.items()}
        self._lower = {n.lower(): n for n in self.by_output}
        for r in recipes:
            for m in r["materials"]:
                if m.get("name"):
                    self._lower.setdefault(m["name"].lower(), m["name"])

    @classmethod
    def load(cls, data_dir=DATA):
        return cls(json.loads((data_dir / "recipes.json").read_text(encoding="utf-8")),
                   json.loads((data_dir / "power.json").read_text(encoding="utf-8")))

    # ---------- lookup ----------
    def gear(self, pmin, pmax):
        """[(name, power, kind)] craftable armour/weapons with pmin <= power <= pmax, sorted by power then name."""
        out = [(n, p, k) for n, (p, k) in self.power.items()
               if p is not None and pmin <= p <= pmax and n in self.by_output]
        return sorted(out, key=lambda t: (t[1], t[0]))

    def primary(self, item):
        """The recipe used for chains: prefer one that doesn't need salvage piles."""
        rs = self.by_output.get(item)
        if not rs:
            return None
        return next((r for r in rs if not any("Salvage" in m["name"] for m in r["materials"])), rs[0])

    def canonical(self, name):
        return self._lower.get(name.strip().lower())

    # ---------- chains ----------
    def tree(self, item, qty=1, _stack=()):
        """Nested ingredient tree: {name, qty, facility, crafts, children:[...]}; raw items have facility None."""
        r = self.primary(item) if item not in _stack else None   # cycle guard
        if r is None:
            return {"name": item, "qty": qty, "facility": None, "crafts": 0, "children": []}
        crafts = math.ceil(qty / r["output_qty"])
        kids = [self.tree(m["name"], m["qty"] * crafts, _stack + (item,)) for m in r["materials"]]
        return {"name": item, "qty": qty, "facility": r["facility"], "crafts": crafts, "children": kids,
                "alternatives": len(self.by_output[item]) - 1}

    def missing(self, item, qty=1, have=None):
        """Raw materials still to gather. Uses what you carry first at every level
        (if you have Iron Bars it won't ask for Iron Ore). Returns (missing_raw {name: qty}, used {name: qty})."""
        stock = dict(have or {})
        need, used = {}, {}

        def walk(name, q, stack):
            take = min(stock.get(name, 0), q)
            if take:
                stock[name] -= take
                used[name] = used.get(name, 0) + take
                q -= take
            if q <= 0:
                return
            r = self.primary(name) if name not in stack else None
            if r is None:
                need[name] = need.get(name, 0) + q
                return
            crafts = math.ceil(q / r["output_qty"])
            for m in r["materials"]:
                walk(m["name"], m["qty"] * crafts, stack + (name,))

        # the top item itself: don't count one you already carry as "used up"
        r = self.primary(item)
        if r is None:
            return {item: qty}, {}
        crafts = math.ceil(qty / r["output_qty"])
        for m in r["materials"]:
            walk(m["name"], m["qty"] * crafts, (item,))
        return need, used

    # ---------- "I have" text ----------
    def parse_inventory(self, text):
        """'iron ore 5, coal 2' / '5 iron ore' / one per line -> ({canonical name: qty}, [unknown names])."""
        have, unknown = {}, []
        for part in re.split(r"[,;\n]+", text):
            part = part.strip()
            if not part:
                continue
            m = re.fullmatch(r"(\d+)\s*x?\s+(.+)|(.+?)\s*[x:]?\s*(\d+)", part, re.I)
            if m:
                q, name = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
            else:
                q, name = "1", part
            canon = self.canonical(name)
            if canon:
                have[canon] = have.get(canon, 0) + int(q)
            else:
                unknown.append(name)
        return have, unknown


# Raw material -> resource node on the map. Rules first, then manual overrides (verified names only).
MANUAL_NODE = {
    "Coal": "Coal Node",
    "Clay": "Clay Node",
    "Flax": "Flax",
    "Cabbage": "Cabbage",
}


def node_for(material, resource_names):
    if material in MANUAL_NODE and MANUAL_NODE[material] in resource_names:
        return MANUAL_NODE[material]
    base = re.sub(r"\s+(Ore|Logs?)$", "", material)
    for cand in (f"{material} Node", f"{base} Ore Node", f"{base} Tree", f"{material} Deposit",
                 f"{material} Rock", f"{material} Bush", material):
        if cand in resource_names:
            return cand
    return None
