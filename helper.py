"""Dragonwilds helper - resource finder (minimal version).

Control window (normal window, takes focus): pick a resource, see it on the map, right-click where you are.
Overlay (top-right, semi-transparent, click-through, never takes focus): the nearest nodes from your pin.

  .venv/Scripts/python helper.py           run
  .venv/Scripts/python helper.py --smoke          self-test: open, check view math, print, exit
  .venv/Scripts/python helper.py --smoke --shots  same + screenshot our two windows to data/smoke_*.png

Hotkeys: F9 overlay on/off, F10 bring up the control window.
  (Key state is only READ via GetAsyncKeyState; nothing is ever sent to the game.)
Map mouse: drag = pan, wheel = zoom, right-click = "I'm here".
The game must run in borderless/windowed mode for the overlay to be visible on top of it.
"""
import argparse
import ctypes
import json
import math
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

import dwdata as dw
import drops as drp
import recipes as rc

# ---------------- config ----------------
NEAREST_K = 5
OVERLAY_ALPHA = 210              # 0..255
OVERLAY_MARGIN = 20              # px from the top-right screen corner
OVERLAY_CHARS = 38               # overlay width in characters
VK_OVERLAY, VK_CONTROL = 0x78, 0x79   # F9, F10 (not used by the game's default binds)
MAX_ZOOM = 3.0                   # screen px per map px
POWER_RANGE = (3, 6)             # default gear power levels shown in the Recipes tab
OVERLAY_MISSING_LINES = 7        # max "still to gather" lines on the overlay
DEFAULT_RESOURCE = "Iron Ore Node"
BG, FG, DIM, BOX = "#161b22", "#e6e6e6", "#8b949e", "#0d1117"
DOT, NEAR, PIN = "#ff4040", "#ffd23f", "#3fe0ff"
# ----------------------------------------

STATE_FILE = Path(__file__).with_name("state.json")
HELP = ("Drag = pan   Wheel = zoom\n"
        "Right-click = I'm here\n"
        "F9 overlay on/off   F10 this window\n"
        "Distances assume 1 unit = 1 cm (est.)\n"
        "N = map up")

# ---------------- Win32: window styles + key state only ----------------
user32 = ctypes.windll.user32
user32.GetParent.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetWindowLongW.restype = ctypes.c_long
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [wintypes.UINT]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]

GWL_EXSTYLE = -20
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW = 0x80000, 0x20, 0x08000000, 0x80
OVERLAY_EXSTYLE = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
LWA_ALPHA = 0x2
HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4


def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


class Overlay:
    """Always-on-top, semi-transparent, click-through, no-focus window (same styles as head_look.py)."""

    def __init__(self, root):
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.label = tk.Label(self.win, justify="left", anchor="nw", width=OVERLAY_CHARS, bg="#0d1117", fg=FG,
                              font=("Consolas", 10), padx=10, pady=8)
        self.label.pack()
        self.win.update_idletasks()
        self.hwnd = user32.GetParent(self.win.winfo_id()) or self.win.winfo_id()
        style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, style | OVERLAY_EXSTYLE)
        user32.SetLayeredWindowAttributes(self.hwnd, 0, OVERLAY_ALPHA, LWA_ALPHA)
        self.visible = True
        self._topmost()

    def _topmost(self):
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def exstyle_ok(self):
        return user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE) & OVERLAY_EXSTYLE == OVERLAY_EXSTYLE

    def set_text(self, text):
        self.label.config(text=text)
        self.win.update_idletasks()
        x = self.win.winfo_screenwidth() - self.win.winfo_reqwidth() - OVERLAY_MARGIN
        self.win.geometry(f"+{x}+{OVERLAY_MARGIN}")

    def set_visible(self, visible):
        self.visible = visible
        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE if visible else SW_HIDE)
        if visible:
            self._topmost()


class App:
    def __init__(self, root, persist=True):
        self.root, self.persist = root, persist
        self.T = dw.MapTransform.load()
        raw = dw.load_resources()
        self.resources = {n: [p for p in pts if self.T.on_map(p)] for n, pts in raw.items()}
        self.offmap = {n: len(raw[n]) - len(self.resources[n]) for n in raw}
        # drop sources (monsters etc.); "layers" = everything that can be shown on the map
        self.drops = drp.DropTable.load()
        self.layers = dict(self.resources)
        for n, pts in self.drops.points.items():
            if n not in self.layers:
                on = [p for p in pts if self.T.on_map(p)]
                self.offmap[n] = len(pts) - len(on)
                self.layers[n] = on
        full = Image.open(dw.DATA / "map_z3.png").convert("RGB")
        self.pyramid = {1: full, 2: full.reduce(2), 4: full.reduce(4)}  # pick a smaller image when zoomed out
        self.map_w, self.map_h = full.size

        st = self._load_state()
        self.selected = st.get("resource") if st.get("resource") in self.layers else DEFAULT_RESOURCE
        if self.selected not in self.resources:
            self.selected = next(iter(self.resources))
        self.pin = tuple(st["pin"]) if st.get("pin") else None
        self.nearest = []
        self.scale = None            # screen px per map px; None until the canvas has a size
        self.ox = self.oy = 0.0      # map px shown at the canvas top-left
        self._redraw_pending = False
        self._drag = None
        self._photo = None
        self.overlay = None

        # recipes
        self.book = rc.RecipeBook.load()
        self.pmin, self.pmax = st.get("power", POWER_RANGE)
        self.recipe_item = st.get("recipe") if st.get("recipe") in self.book.by_output else None
        self.recipe_qty = int(st.get("recipe_qty", 1))
        self.recipe_on_overlay = st.get("recipe_on_overlay", True)
        self._have_initial = st.get("have", "")
        self.missing_now = {}
        self._have_job = None

        self._build_ui()
        self.overlay = Overlay(root)
        if not st.get("overlay_visible", True):
            self.overlay.set_visible(False)
        self._keys = {VK_OVERLAY: key_down(VK_OVERLAY), VK_CONTROL: key_down(VK_CONTROL)}
        self._poll_keys()
        self.refresh()

    # ---------- state ----------
    def _load_state(self):
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}

    def _save_state(self):
        if not self.persist or self.overlay is None:
            return
        STATE_FILE.write_text(json.dumps({
            "resource": self.selected, "pin": list(self.pin) if self.pin else None,
            "overlay_visible": self.overlay.visible,
            "power": [self.pmin, self.pmax], "recipe": self.recipe_item, "recipe_qty": self.recipe_qty,
            "recipe_on_overlay": self.recipe_on_overlay, "have": self.have_box.get("1.0", "end").strip(),
        }))

    # ---------- UI ----------
    def _build_ui(self):
        r = self.root
        r.title("Dragonwilds helper")
        try:
            r.iconbitmap(default=str(Path(__file__).with_name("helper.ico")))
        except tk.TclError:
            pass
        r.geometry("1250x850")
        r.configure(bg=BG)

        style = ttk.Style(r)
        style.theme_use("clam")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#21262d", foreground=FG, padding=(12, 4))
        style.map("TNotebook.Tab", background=[("selected", "#1f6feb")])

        side = tk.Frame(r, bg=BG)
        side.pack(side="left", fill="y", padx=8, pady=8)
        tk.Label(side, text="Data: dragonwilds.runescape.wiki (CC BY-NC-SA 3.0)", bg=BG, fg=DIM,
                 font=("Segoe UI", 7)).pack(side="bottom", anchor="w")
        tk.Label(side, text=HELP, justify="left", anchor="w", bg=BG, fg=DIM,
                 font=("Segoe UI", 8)).pack(side="bottom", fill="x", pady=(6, 0))
        self.nb = ttk.Notebook(side)
        self.nb.pack(fill="both", expand=True)
        self.res_tab = tk.Frame(self.nb, bg=BG)
        self.rec_tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(self.res_tab, text="Resources")
        self.nb.add(self.rec_tab, text="Recipes")
        self._build_resources_tab(self.res_tab)
        self._build_recipes_tab(self.rec_tab)

        self.canvas = tk.Canvas(r, bg="#1b2630", highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        c = self.canvas
        c.bind("<Configure>", self._on_resize)
        c.bind("<ButtonPress-1>", self._drag_start)
        c.bind("<B1-Motion>", self._drag_move)
        c.bind("<MouseWheel>", self._wheel)
        c.bind("<Button-3>", self._set_pin)
        self._fill_list()

    def _build_resources_tab(self, side):
        tk.Label(side, text="Search resource", bg=BG, fg=DIM, anchor="w").pack(fill="x", pady=(6, 0))
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self._fill_list())
        tk.Entry(side, textvariable=self.search, bg=BOX, fg=FG, insertbackground=FG, width=32).pack(fill="x")
        self.listbox = tk.Listbox(side, height=20, exportselection=False, activestyle="none", bg=BOX, fg=FG,
                                  selectbackground="#1f6feb", highlightthickness=0, font=("Segoe UI", 9))
        self.listbox.pack(fill="both", expand=True, pady=(4, 8))
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        self.info = tk.Label(side, justify="left", anchor="w", bg=BG, fg=FG, font=("Consolas", 9),
                             width=40)  # fixed width so the sidebar (and map) don't jump when text changes
        self.info.pack(fill="x")
        btns = tk.Frame(side, bg=BG)
        btns.pack(fill="x", pady=6)
        for text, cmd in (("Fit map", self.fit), ("Center on pin", self.center_on_pin), ("Clear pin", self.clear_pin)):
            tk.Button(btns, text=text, command=cmd).pack(side="left", padx=(0, 4))

    def _build_recipes_tab(self, side):
        row = tk.Frame(side, bg=BG)
        row.pack(fill="x", pady=(6, 2))
        tk.Label(row, text="Gear power", bg=BG, fg=DIM).pack(side="left")
        self.pmin_var, self.pmax_var = tk.IntVar(value=self.pmin), tk.IntVar(value=self.pmax)
        for var, lbl in ((self.pmin_var, None), (self.pmax_var, "to")):
            if lbl:
                tk.Label(row, text=lbl, bg=BG, fg=DIM).pack(side="left", padx=2)
            tk.Spinbox(row, from_=0, to=9, width=3, textvariable=var, command=self._power_changed,
                       bg=BOX, fg=FG, buttonbackground="#21262d").pack(side="left", padx=2)
        tk.Label(row, text="Amount", bg=BG, fg=DIM).pack(side="left", padx=(12, 2))
        self.qty_var = tk.IntVar(value=self.recipe_qty)
        tk.Spinbox(row, from_=1, to=99, width=3, textvariable=self.qty_var, command=self._recipe_update,
                   bg=BOX, fg=FG, buttonbackground="#21262d").pack(side="left")

        self.rsearch = tk.StringVar()
        self.rsearch.trace_add("write", lambda *_: self._fill_recipe_list())
        tk.Entry(side, textvariable=self.rsearch, bg=BOX, fg=FG, insertbackground=FG).pack(fill="x", pady=2)
        self.rlist = tk.Listbox(side, height=9, exportselection=False, activestyle="none", bg=BOX, fg=FG,
                                selectbackground="#1f6feb", highlightthickness=0, font=("Segoe UI", 9))
        self.rlist.pack(fill="x")
        self.rlist.bind("<<ListboxSelect>>", self._on_recipe_select)

        self.tree_box = self._text(side, 11)
        tk.Label(side, text="I have (e.g. iron ore 5, coal 2):", bg=BG, fg=DIM, anchor="w").pack(fill="x")
        self.have_box = tk.Text(side, height=3, width=42, bg=BOX, fg=FG, insertbackground=FG, wrap="word",
                                font=("Consolas", 9), highlightthickness=0)
        self.have_box.insert("1.0", self._have_initial)
        self.have_box.pack(fill="x")
        self.have_box.bind("<KeyRelease>", self._have_changed)
        self.miss_box = self._text(side, 9)
        self.ov_var = tk.BooleanVar(value=self.recipe_on_overlay)
        tk.Checkbutton(side, text="Show missing list on overlay", variable=self.ov_var, command=self._recipe_update,
                       bg=BG, fg=FG, selectcolor=BOX, activebackground=BG, activeforeground=FG).pack(anchor="w")
        self._fill_recipe_list()

    def _text(self, parent, height):
        t = tk.Text(parent, height=height, width=42, bg=BOX, fg=FG, wrap="none", font=("Consolas", 9),
                    highlightthickness=0, cursor="arrow")
        t.pack(fill="x", pady=4)
        t.tag_configure("dim", foreground=DIM)
        t.tag_configure("head", foreground=NEAR)
        t.tag_configure("link", foreground="#58a6ff", underline=True)
        t.configure(state="disabled")
        return t

    def _fill_list(self):
        q = self.search.get().strip().lower()
        self.names = [n for n in self.resources if q in n.lower()]
        self.listbox.delete(0, "end")
        for n in self.names:
            self.listbox.insert("end", f"{n}  ({len(self.resources[n])})")
        if self.selected in self.names:
            i = self.names.index(self.selected)
            self.listbox.selection_set(i)
            self.listbox.see(i)

    def _on_select(self, _e):
        sel = self.listbox.curselection()
        if sel:
            self.selected = self.names[sel[0]]
            self._save_state()
            self.refresh()

    # ---------- recipes ----------
    def _power_changed(self):
        try:
            self.pmin, self.pmax = sorted((int(self.pmin_var.get()), int(self.pmax_var.get())))
        except (tk.TclError, ValueError):
            return
        self._fill_recipe_list()
        self._save_state()

    def _fill_recipe_list(self):
        q = self.rsearch.get().strip().lower()
        self.rnames = [(n, p, k) for n, p, k in self.book.gear(self.pmin, self.pmax) if q in n.lower()]
        self.rlist.delete(0, "end")
        for n, p, k in self.rnames:
            self.rlist.insert("end", f"[{p}] {n}  ({k})")
        names = [n for n, _, _ in self.rnames]
        if self.recipe_item in names:
            i = names.index(self.recipe_item)
            self.rlist.selection_set(i)
            self.rlist.see(i)
        self._recipe_update()

    def _on_recipe_select(self, _e):
        sel = self.rlist.curselection()
        if sel:
            self.recipe_item = self.rnames[sel[0]][0]
            self._recipe_update()

    def _have_changed(self, _e):
        if self._have_job:   # wait until typing pauses
            self.root.after_cancel(self._have_job)
        self._have_job = self.root.after(400, self._recipe_update)

    def _goto_node(self, node):
        """Show a map layer (resource node or drop source such as 'Deer')."""
        self.selected = node
        self.nb.select(self.res_tab)
        self.search.set("")
        self._fill_list()
        if node not in self.resources:          # drop source: not in the resource list
            self.listbox.selection_clear(0, "end")
        self._save_state()
        self.refresh()

    def _write(self, box, parts):
        """parts: [(text, tag_or_None, action_or_None)]; action = layer name (map link) or a callable."""
        box.configure(state="normal")
        box.delete("1.0", "end")
        for i, (text, tag, action) in enumerate(parts):
            if action:
                t = f"link{i}"
                box.insert("end", text, ("link", t))
                cb = action if callable(action) else (lambda n=action: self._goto_node(n))
                box.tag_bind(t, "<Button-1>", lambda _e, f=cb: f())
            else:
                box.insert("end", text, tag or ())
        box.configure(state="disabled")

    def _map_link(self, material):
        node = rc.node_for(material, self.resources)
        if node:
            return [("  [map]", None, node)]
        if self.drops.has(material):
            return [("  [where?]", None, lambda m=material: self._show_where(m))]
        return []

    def _show_where(self, item):
        """Popup: every source of an item, best chance first, with map links where the wiki has positions."""
        if getattr(self, "where_win", None) is None or not self.where_win.winfo_exists():
            self.where_win = tk.Toplevel(self.root, bg=BG)
            self.where_win.transient(self.root)
            self.where_win.geometry(f"+{self.root.winfo_rootx() + 40}+{self.root.winfo_rooty() + 80}")
            self.where_box = tk.Text(self.where_win, width=52, height=22, bg=BOX, fg=FG, wrap="none",
                                     font=("Consolas", 9), highlightthickness=0, cursor="arrow")
            self.where_box.pack(fill="both", expand=True, padx=6, pady=6)
            for tag, color in (("dim", DIM), ("head", NEAR)):
                self.where_box.tag_configure(tag, foreground=color)
            self.where_box.tag_configure("link", foreground="#58a6ff", underline=True)
        self.where_win.title(f"Where to get {item}")
        rows = self.drops.sources(item)
        parts = [(f"Where to get {item}  ({len(rows)} sources)\n", "head", None),
                 ("chance   source\n", "dim", None)]
        for r in rows[:40]:
            qty = f" x{r['qty']}" if r["qty"] not in ("?", "1", 1) else ""
            parts.append((f"{r['rarity']:>8}  {r['source']}{qty}", None, None))
            if r["map"]:
                parts.append(("  [map]", None, r["map"]))
            parts.append(("\n", None, None))
        if len(rows) > 40:
            parts.append((f"... +{len(rows) - 40} more\n", "dim", None))
        parts.append(("\n[map] = the wiki has spawn positions for it.\n", "dim", None))
        self._write(self.where_box, parts)
        self.where_win.deiconify()
        self.where_win.lift()
        self.last_where = rows

    def _recipe_update(self):
        try:
            self.recipe_qty = max(1, int(self.qty_var.get()))
        except (tk.TclError, ValueError):
            pass
        self.recipe_on_overlay = bool(self.ov_var.get())
        item = self.recipe_item
        if not item:
            self._write(self.tree_box, [("Pick an item above.", "dim", None)])
            self._write(self.miss_box, [])
            self.missing_now = {}
            self.refresh()
            return

        parts = []

        def walk(node, depth):
            fmt = f"{node['qty']:g}"
            parts.append(("  " * depth + f"{node['name']} x{fmt}", "head" if depth == 0 else None, None))
            if node["facility"]:
                extra = f" (+{node['alternatives']} alt)" if node.get("alternatives") else ""
                parts.append((f"  - {node['facility']}{extra}", "dim", None))
            else:
                parts.extend(self._map_link(node["name"]))
            parts.append(("\n", None, None))
            for ch in node["children"]:
                walk(ch, depth + 1)

        walk(self.book.tree(item, self.recipe_qty), 0)
        self._write(self.tree_box, parts)

        have, unknown = self.book.parse_inventory(self.have_box.get("1.0", "end"))
        need, used = self.book.missing(item, self.recipe_qty, have)
        self.missing_now = need
        mp = []
        if need:
            mp.append(("Still to gather:\n", "head", None))
            for name, q in sorted(need.items(), key=lambda kv: -kv[1]):
                mp.append((f"  {name} {q:g}", None, None))
                mp.extend(self._map_link(name))
                mp.append(("\n", None, None))
        else:
            mp.append(("Nothing missing - go craft it!\n", "head", None))
        if used:
            mp.append(("From your bag: " + ", ".join(f"{n} {q:g}" for n, q in used.items()) + "\n", "dim", None))
        if unknown:
            mp.append(("Didn't recognise: " + ", ".join(unknown) + "\n", "dim", None))
        self._write(self.miss_box, mp)
        self._save_state()
        self.refresh()

    def _recipe_overlay_lines(self):
        if not (self.recipe_item and self.recipe_on_overlay):
            return []
        out = ["", f"Craft: {self.recipe_item} x{self.recipe_qty}"]
        if not self.missing_now:
            return out + [" nothing missing!"]
        items = sorted(self.missing_now.items(), key=lambda kv: -kv[1])
        for name, q in items[:OVERLAY_MISSING_LINES]:
            out.append(f" {q:>5g}  {name}")
        if len(items) > OVERLAY_MISSING_LINES:
            out.append(f"  +{len(items) - OVERLAY_MISSING_LINES} more")
        return out

    # ---------- view ----------
    def _canvas_size(self):
        return max(self.canvas.winfo_width(), 50), max(self.canvas.winfo_height(), 50)

    def _on_resize(self, _e):
        if self.scale is None:
            self.fit()
        else:
            self.request_redraw()

    def fit(self):
        cw, ch = self._canvas_size()
        self.scale = min(cw / self.map_w, ch / self.map_h)
        self.ox = -(cw / self.scale - self.map_w) / 2
        self.oy = -(ch / self.scale - self.map_h) / 2
        self.request_redraw()

    def center_on_pin(self, zoom=0.75):
        if not self.pin or self.scale is None:
            return
        cw, ch = self._canvas_size()
        self.scale = max(self.scale, zoom)
        px, py = self.T.to_px(*self.pin)
        self.ox, self.oy = px - cw / 2 / self.scale, py - ch / 2 / self.scale
        self.request_redraw()

    def clear_pin(self):
        self.pin = None
        self._save_state()
        self.refresh()

    def _drag_start(self, e):
        self._drag = (e.x, e.y, self.ox, self.oy)

    def _drag_move(self, e):
        if self._drag and self.scale:
            x0, y0, ox, oy = self._drag
            self.ox, self.oy = ox - (e.x - x0) / self.scale, oy - (e.y - y0) / self.scale
            self.request_redraw()

    def _wheel(self, e):
        if self.scale is None:
            return
        cw, ch = self._canvas_size()
        fit = min(cw / self.map_w, ch / self.map_h)
        new = min(MAX_ZOOM, max(fit * 0.8, self.scale * (1.25 if e.delta > 0 else 0.8)))
        mx, my = self.ox + e.x / self.scale, self.oy + e.y / self.scale   # keep the point under the cursor fixed
        self.scale = new
        self.ox, self.oy = mx - e.x / new, my - e.y / new
        self.request_redraw()

    def _set_pin(self, e):
        if self.scale is None:
            return
        self.pin = self.T.to_game(self.ox + e.x / self.scale, self.oy + e.y / self.scale)
        self._save_state()
        self.refresh()

    # ---------- content ----------
    def _summary_lines(self):
        pts = self.layers.get(self.selected, [])
        head = [f"{self.selected}  ({len(pts)} on map)"]
        if self.offmap.get(self.selected):
            head.append(f"  +{self.offmap[self.selected]} off-map (interiors?), not shown")
        if not self.pin:
            return head + ["", "Right-click the map (control window)", "to set your position."]
        out = head + ["Nearest to your pin:"]
        for i, (d, p) in enumerate(self.nearest, 1):
            out.append(f" {i}. {dw.fmt_distance(d):>8}  {dw.compass(dw.bearing_deg(self.pin, p))}")
        return out

    def refresh(self):
        pts = self.layers.get(self.selected, [])
        self.nearest = dw.nearest(pts, self.pin, NEAREST_K) if self.pin else []
        lines = self._summary_lines()
        self.info.config(text="\n".join(lines))
        if self.overlay:
            self.overlay.set_text("\n".join(lines + self._recipe_overlay_lines()
                                            + ["", "F9 hide  ·  F10 control window"]))
        self.request_redraw()

    def request_redraw(self):
        if not self._redraw_pending:   # coalesce bursts of drag/wheel events into one redraw
            self._redraw_pending = True
            self.root.after_idle(self._redraw)

    def _to_screen(self, gx, gy):
        px, py = self.T.to_px(gx, gy)
        return (px - self.ox) * self.scale, (py - self.oy) * self.scale

    def _redraw(self):
        self._redraw_pending = False
        if self.scale is None:
            return
        c = self.canvas
        c.delete("all")
        cw, ch = self._canvas_size()
        s, ox, oy = self.scale, self.ox, self.oy

        # map image: crop the visible part of the best pyramid level, scale it to the screen
        f = max([k for k in self.pyramid if s * k <= 1.0], default=1)
        img = self.pyramid[f]
        x0, y0 = max(0, int(ox / f)), max(0, int(oy / f))
        x1 = min(img.width, math.ceil((ox + cw / s) / f))
        y1 = min(img.height, math.ceil((oy + ch / s) / f))
        if x1 > x0 and y1 > y0:
            w, h = max(1, round((x1 - x0) * f * s)), max(1, round((y1 - y0) * f * s))
            crop = img.crop((x0, y0, x1, y1)).resize((w, h), Image.Resampling.BILINEAR)
            self._photo = ImageTk.PhotoImage(crop)
            c.create_image((x0 * f - ox) * s, (y0 * f - oy) * s, image=self._photo, anchor="nw")

        # resource dots (only those on screen)
        r = 3 if s < 0.5 else 4 if s < 1.2 else 5
        for gx, gy in self.layers.get(self.selected, []):
            x, y = self._to_screen(gx, gy)
            if -r <= x <= cw + r and -r <= y <= ch + r:
                c.create_oval(x - r, y - r, x + r, y + r, fill=DOT, outline="white")

        # pin + nearest
        if self.pin:
            px, py = self._to_screen(*self.pin)
            for i, (_, p) in enumerate(self.nearest, 1):
                x, y = self._to_screen(*p)
                c.create_line(px, py, x, y, fill=NEAR, dash=(4, 3))
                c.create_oval(x - 8, y - 8, x + 8, y + 8, outline=NEAR, width=2)
                c.create_text(x + 12, y - 12, text=str(i), fill=NEAR, font=("Segoe UI", 10, "bold"))
            c.create_line(px - 14, py, px + 14, py, fill=PIN, width=2)
            c.create_line(px, py - 14, px, py + 14, fill=PIN, width=2)
            c.create_oval(px - 6, py - 6, px + 6, py + 6, fill=PIN, outline="black", width=2)

    # ---------- hotkeys (read-only polling) ----------
    def _poll_keys(self):
        for vk, was in self._keys.items():
            down = key_down(vk)
            if down and not was:
                if vk == VK_OVERLAY:
                    self.overlay.set_visible(not self.overlay.visible)
                    self._save_state()
                else:
                    self.show_control()
            self._keys[vk] = down
        self.root.after(50, self._poll_keys)

    def show_control(self):
        r = self.root
        r.deiconify()
        r.lift()
        r.attributes("-topmost", True)            # Windows may refuse focus stealing; topmost blip helps
        r.after(300, lambda: r.attributes("-topmost", False))
        r.focus_force()


def smoke(app, root, shots=False):
    """Open both windows, test the pin/zoom path, print the numbers, exit.
    With shots=True also screenshot our two window rectangles (control window is forced on top first,
    but anything behind the semi-transparent overlay can still show through faintly)."""
    from PIL import ImageGrab

    def grab(win, name):
        if not shots:
            return
        root.attributes("-topmost", True)
        root.update()
        root.after(200)
        x, y = win.winfo_rootx(), win.winfo_rooty()
        bbox = (x, y, x + win.winfo_width(), y + win.winfo_height())
        ImageGrab.grab(bbox=bbox, include_layered_windows=True, all_screens=True).save(dw.DATA / f"smoke_{name}.png")
        print(f"saved smoke_{name}.png  bbox={bbox}")

    def step1():
        grab(root, "control_fit")
        grab(app.overlay.win, "overlay_nopin")
        iron = app.resources[app.selected][0]
        app.pin = (iron[0] + 4000, iron[1] + 3000)  # test pin near the first node (not saved)
        app.refresh()
        app.center_on_pin(zoom=1.0)
        root.after(800, step2)

    def step2():
        grab(root, "control_zoomed")
        grab(app.overlay.win, "overlay_pin")
        print("overlay exstyle flags ok:", app.overlay.exstyle_ok())
        print("view: scale", round(app.scale, 3), "canvas", app._canvas_size(),
              "pin on screen", [round(v) for v in app._to_screen(*app.pin)])
        print("nearest:", [(round(d), p) for d, p in app.nearest])
        # recipe path
        print("recipe list (power %d-%d): %d items" % (app.pmin, app.pmax, len(app.rnames)))
        app.recipe_item = "Iron Platebody"
        app.have_box.insert("1.0", "iron bar 4, hard leather 2, blah 3")
        app._recipe_update()
        print("missing:", app.missing_now)
        print("tree box:\n" + app.tree_box.get("1.0", "end").rstrip())
        print("miss box:\n" + app.miss_box.get("1.0", "end").rstrip())
        print("overlay:\n" + app.overlay.label.cget("text"))
        app._goto_node("Iron Ore Node")
        print("map link jump ->", app.selected, "| tab:", app.nb.tab(app.nb.select(), "text"))
        # where-to-get path
        app._show_where("Animal Hide")
        print("where popup:\n" + app.where_box.get("1.0", "end").rstrip())
        app._goto_node("Deer")
        print("deer layer:", app.selected, len(app.layers["Deer"]), "points | info:\n" + app.info.cget("text"))
        root.destroy()

    root.after(1500, step1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="self-test: open, check, print, exit")
    ap.add_argument("--shots", action="store_true", help="with --smoke: also screenshot our windows")
    a = ap.parse_args()
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # crisp text; Tk coords = real pixels
    except Exception:
        pass
    root = tk.Tk()
    app = App(root, persist=not a.smoke)
    if a.smoke:
        smoke(app, root, shots=a.shots)
    root.mainloop()


if __name__ == "__main__":
    main()
