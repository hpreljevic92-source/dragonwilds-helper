"""OFFLINE feasibility test: find which part of the world an in-game map screenshot shows.

Reads a saved screenshot file only (no live capture, nothing touches the game).
  python tools/match_map.py "C:/path/to/screenshot.png" ["Iron Ore Node"]
  python tools/match_map.py --selftest      # fake 'screenshot' cut from the wiki map, to check the method

Writes data/match_result.png: the screenshot with the resource's dots drawn where the match says they are.
"""
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import dwdata as dw  # noqa: E402

MAP_SCALE = 0.5          # match against a half-size wiki map (1536 px): faster, plenty of detail
SHOT_MAX_W = 1280        # downscale screenshots to this width before matching


def load_gray(path, max_w=None):
    img = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)  # handles non-ASCII paths
    if img is None:
        raise SystemExit(f"cannot read image: {path}")
    f = 1.0
    if max_w and img.shape[1] > max_w:
        f = max_w / img.shape[1]
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    return img, cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), f


def match(shot_gray, map_gray):
    """Similarity transform screenshot-px -> map-px (scale, rotation, shift) + inlier count."""
    sift = cv2.SIFT_create(nfeatures=6000)
    k1, d1 = sift.detectAndCompute(shot_gray, None)
    k2, d2 = sift.detectAndCompute(map_gray, None)
    if d1 is None or d2 is None:
        return None, 0, 0
    pairs = cv2.FlannBasedMatcher({"algorithm": 1, "trees": 5}, {"checks": 64}).knnMatch(d1, d2, k=2)
    good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < 6:
        return None, 0, len(good)
    src = np.float32([k1[m.queryIdx].pt for m in good])
    dst = np.float32([k2[m.trainIdx].pt for m in good])
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=4.0)
    return M, int(inl.sum()) if inl is not None else 0, len(good)


def main():
    args = sys.argv[1:]
    resource = "Iron Ore Node"
    full = cv2.imdecode(np.fromfile(str(dw.DATA / "map_z3.png"), np.uint8), cv2.IMREAD_COLOR)
    small = cv2.resize(full, None, fx=MAP_SCALE, fy=MAP_SCALE, interpolation=cv2.INTER_AREA)
    map_gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    if args and args[0] == "--selftest":
        # fake screenshot: a 1600x900 crop of the full map, zoomed 1.3x, slightly darkened
        x, y = 100, 1200
        crop = cv2.resize(full[y:y + 700, x:x + 1240], (1600, 903))
        crop = cv2.convertScaleAbs(crop, alpha=0.85, beta=10)
        shot, shot_gray, f = crop, cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), 1.0
        truth = (x, y, 1240 / 1600)
    elif args:
        shot, shot_gray, f = load_gray(args[0], SHOT_MAX_W)
        resource = args[1] if len(args) > 1 else resource
        truth = None
    else:
        raise SystemExit(__doc__)

    t = time.time()
    M, inliers, good = match(shot_gray, map_gray)
    dt = time.time() - t
    print(f"good matches {good}, inliers {inliers}, time {dt:.2f}s")
    if M is None or inliers < 12:
        print("RESULT: no reliable match (need >= 12 inliers)")
        return
    scale = float(np.hypot(M[0, 0], M[1, 0]))
    rot = float(np.degrees(np.arctan2(M[1, 0], M[0, 0])))
    print(f"screenshot px -> half-map px: scale {scale:.3f}, rotation {rot:.2f} deg, shift ({M[0, 2]:.0f}, {M[1, 2]:.0f})")
    if truth:
        tx, ty, ts = truth
        print(f"expected (full-map px): x0 {tx}, y0 {ty}, scale {ts:.3f}")
        print(f"got      (full-map px): x0 {M[0, 2] / MAP_SCALE:.0f}, y0 {M[1, 2] / MAP_SCALE:.0f}, "
              f"scale {scale / MAP_SCALE:.3f}")

    # project resource points into the screenshot: game -> full map px -> half map px -> screenshot px
    T = dw.MapTransform.load()
    pts = json.loads((dw.DATA / "resources" / f"{resource}.json").read_text(encoding="utf-8"))
    Minv = cv2.invertAffineTransform(M)
    out = shot.copy()
    h, w = out.shape[:2]
    shown = 0
    for p in pts:
        px, py = T.to_px(p["x"], p["y"])
        sx, sy = Minv @ np.array([px * MAP_SCALE, py * MAP_SCALE, 1.0])
        if 0 <= sx < w and 0 <= sy < h:
            shown += 1
            cv2.circle(out, (int(sx), int(sy)), 6, (40, 40, 255), -1)
            cv2.circle(out, (int(sx), int(sy)), 6, (255, 255, 255), 1)
    cv2.putText(out, f"{resource}: {shown} on screen | inliers {inliers}", (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    ok, buf = cv2.imencode(".png", out)
    buf.tofile(str(dw.DATA / "match_result.png"))
    print(f"RESULT: match ok, {shown} {resource} dots drawn -> data/match_result.png")


if __name__ == "__main__":
    main()
