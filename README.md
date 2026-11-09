# Dragonwilds Helper

A small, unofficial companion app for **RuneScape: Dragonwilds** (Windows): a resource map, gear recipes with a
"what am I missing?" list, drop sources, and an always-on-top overlay. Think RuneLite-style helper, but **outside**
the game.

> Not affiliated with or endorsed by Jagex. All data comes from the community
> [Dragonwilds Wiki](https://dragonwilds.runescape.wiki) (CC BY-NC-SA 3.0).

## What it does

- **Resource finder:** pick a resource (iron, coal, oak, fishing spots, …) and see every node on the world map.
  Right-click where you are and it lists the **5 nearest** with distance and direction.
- **Recipes:** armour and weapons filtered by **power level** (default 3–6). It shows the full ingredient chain
  (e.g. Iron Platebody → Iron Bar → Iron Ore) and the station for each step.
- **"I have…":** type what you carry (`iron bar 4, hard leather 2`) and it lists what is still missing, all the way
  down to raw materials.
- **Where to get it:** for monster and chest drops (Animal Hide, Fleece, Swamp Tar, …) it lists every source by
  drop chance. Click `[map]` to see where that monster spawns.
- **Overlay:** a small see-through box in the top-right corner shows the nearest nodes and your missing list.
  Clicks pass through it and it never takes focus from the game.

## What it does NOT do

No memory reading, no game-file or network access, no input automation, no bots. It never presses keys or clicks
for you. It only **reads** the state of two hotkeys (F9/F10) so you can toggle its own windows.
Jagex's rules forbid software that plays for you, so this tool deliberately doesn't.

## Install (Windows, Python 3.11+)

```powershell
git clone https://github.com/hpreljevic92-source/dragonwilds-helper.git
cd dragonwilds-helper
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install Pillow
```

Download the data once (about 15 MB, polite: 1 request per second, cached in `data/`):

```powershell
.\.venv\Scripts\python.exe fetch_data.py --resources --map 3 --recipes --drops
```

Optional: make an icon and a desktop shortcut:

```powershell
.\.venv\Scripts\python.exe tools\make_icon.py
powershell -ExecutionPolicy Bypass -File tools\make_shortcut.ps1
```

## Use

Start it by double-clicking **`Start Dragonwilds Helper.bat`** (or the desktop shortcut).
Set the game to **borderless** or **windowed** mode, because overlays can't show over exclusive fullscreen.

| Where | How |
|---|---|
| Map | drag = pan, mouse wheel = zoom, **right-click = "I'm here"** |
| Resources tab | search and pick a resource; Fit map / Center on pin / Clear pin |
| Recipes tab | set gear power range and amount, pick an item, type what you have |
| `[map]` / `[where?]` | jump to nodes on the map / show drop sources |
| **F9** | overlay on/off |
| **F10** | bring the control window to the front |

Your last resource, pin and inventory text are saved in `state.json` (not shared, git-ignored).

## Updating data after a game patch

```powershell
.\.venv\Scripts\python.exe fetch_data.py --resources --recipes --drops --force
```

## Known limits

- Distances assume 1 game unit = 1 cm (Unreal Engine). Not confirmed for this game.
- "North" = up on the map.
- About 0.8% of the wiki's node positions lie outside the map (probably vault or cave interiors). They are hidden and counted.
- Monsters roam, so spawn points are approximate. Some sources (vault monsters, chests) have no positions on the wiki.
- Wiki data can lag behind game patches.

## Developers

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v   # logic tests (needs downloaded data)
.\.venv\Scripts\python.exe helper.py --smoke                   # opens the windows, self-checks, exits
```

`tools/match_map.py` is an **experimental offline test** for matching a saved in-game map screenshot to the
world map (needs `opencv-python`). It reads image files only, with no live capture.

| File | What |
|---|---|
| `helper.py` | UI: control window + overlay |
| `dwdata.py` | map transform, distances, nearest nodes |
| `recipes.py` | power filter, ingredient chains, missing list |
| `drops.py` | drop sources sorted by chance |
| `fetch_data.py` | one-time wiki download |

## License

Code: MIT (see `LICENSE`). Data and map images are **not** included. They are downloaded from the
Dragonwilds Wiki (CC BY-NC-SA 3.0); game content © Jagex.
