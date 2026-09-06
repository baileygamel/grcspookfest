#!/usr/bin/env python3
"""
Turn base-character contact sheets into individual avatar PNGs.

One sheet = one base character; every cell on it is a variant of that same
character. Sheets arrive in a few shapes, so this handles all of them:

  * .svg   the background-removed export from the design tool. It isn't really
           vector — it's the original raster plus a luminance mask — so it gets
           unwrapped into real RGBA (see svg_to_rgba.py).
  * .png   with alpha: used as-is.
  * .png   without alpha: the generator paints a fake checkerboard instead of
           being transparent, so that gets flood-filled away from the border.

Usage:
    python3 tools/slice_sheet.py                  # every sheet in tools/sheets
    python3 tools/slice_sheet.py tools/sheets/x.json

Writes assets/<id>/01.png … and rebuilds characters.js.
"""
import json, os, sys
from collections import Counter, deque
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from svg_to_rgba import unwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEETS = os.path.join(ROOT, "tools", "sheets")
ASSETS = os.path.join(ROOT, "assets")

SEAM_WINDOW = 22          # how far a detected seam may drift from the nominal grid
MIN_SPECK = 40            # opaque islands smaller than this are export noise

# A sheet is 1536x1024, so one avatar is only ~190-240 real pixels wide. On a 2x
# display the big step-3 preview would have to be blown up past life size, and
# the browser's own upscale is mushy — so ship a Lanczos + unsharp @2x beside
# each tile and let the preview use that. Grid tiles stay on the 1x file.
RETINA_SHARPEN = dict(radius=1.6, percent=55, threshold=3)


# ------------------------------------------------------------------ loading --
def load_sheet(path):
    if path.lower().endswith(".svg"):
        return unwrap(path)
    im = Image.open(path)
    if im.mode in ("RGBA", "LA") and im.convert("RGBA").getextrema()[3][0] < 250:
        return im.convert("RGBA")
    return key_out_background(im.convert("RGB"))


def key_out_background(im):
    """Fake-transparency rescue: flood the painted checkerboard in from the
    border, so enclosed light areas (teeth, eye whites) are left alone."""
    W, H = im.size
    px = list(im.getdata())

    def is_bg(i):
        r, g, b = px[i]
        return max(r, g, b) >= 196 and max(r, g, b) - min(r, g, b) <= 18

    seen, mask, dq = bytearray(W * H), bytearray(W * H), deque()
    edge = [(x, y) for x in range(W) for y in (0, H - 1)]
    edge += [(x, y) for y in range(H) for x in (0, W - 1)]
    for x, y in edge:
        i = y * W + x
        if not seen[i] and is_bg(i):
            seen[i] = 1
            dq.append(i)
    while dq:
        i = dq.popleft()
        mask[i] = 1
        x, y = i % W, i // W
        for j in (i - 1 if x else -1, i + 1 if x < W - 1 else -1,
                  i - W if y else -1, i + W if y < H - 1 else -1):
            if j >= 0 and not seen[j] and is_bg(j):
                seen[j] = 1
                dq.append(j)
    alpha = Image.frombytes("L", (W, H), bytes(0 if m else 255 for m in mask))
    return Image.merge("RGBA", (*im.split(), alpha))


def despeckle(im, min_px=MIN_SPECK):
    """Drop stray opaque flecks left behind by background removal."""
    W, H = im.size
    px = im.load()
    seen = bytearray(W * H)
    for sy in range(H):
        for sx in range(W):
            i = sy * W + sx
            if seen[i] or px[sx, sy][3] < 12:
                continue
            comp, dq, seen[i] = [], deque([i]), 1
            while dq:
                j = dq.popleft()
                comp.append(j)
                x, y = j % W, j // W
                for k in (j - 1 if x else -1, j + 1 if x < W - 1 else -1,
                          j - W if y else -1, j + W if y < H - 1 else -1):
                    if k >= 0 and not seen[k] and px[k % W, k // W][3] >= 12:
                        seen[k] = 1
                        dq.append(k)
            if len(comp) < min_px:
                for j in comp:
                    px[j % W, j // W] = (0, 0, 0, 0)
    return im


# --------------------------------------------------------------------- grid --
def seams(profile, start, pitch, count, limit):
    """Nominal grid lines, each nudged onto the thinnest nearby row/column.

    Cells often touch, so there isn't always an empty gap to find — but the
    sheets are machine-regular, so the nominal line is never far off.
    """
    out = []
    for i in range(count + 1):
        nominal = int(round(start + i * pitch))
        lo = max(0, nominal - SEAM_WINDOW)
        hi = min(limit, nominal + SEAM_WINDOW + 1)
        out.append(min(range(lo, hi), key=lambda v: profile[v]) if hi > lo else
                   max(0, min(nominal, limit)))
    return out


def pill_top(px, x0, x1, top, bottom):
    """First row of the label pill fused to the bottom of a bust.

    Sample the pill's flat fill from just inside its bottom edge (below the dark
    label text), then walk up while that colour still spans the row.
    """
    ybot = bottom
    while ybot > top and not any(px[x, ybot][3] for x in range(x0, x1)):
        ybot -= 1
    fill = Counter()
    for y in range(max(top, ybot - 18), ybot):
        for x in range(x0, x1):
            c = px[x, y]
            if c[3] and min(c[0], c[1], c[2]) >= 90:
                fill[c[:3]] += 1
    if not fill:
        return bottom + 1
    f = fill.most_common(1)[0][0]

    def hits(y):
        return sum(1 for x in range(x0, x1)
                   if px[x, y][3] and all(abs(px[x, y][k] - f[k]) <= 24 for k in range(3)))

    floor = top + 60
    solid = [y for y in range(floor, ybot + 1) if hits(y) >= 20]
    if not solid:
        return bottom + 1
    y = max(solid)
    while y > floor and hits(y) >= 8:
        y -= 1
    return y


def content_bbox(px, x0, x1, y0, y1):
    bx0, by0, bx1, by1 = x1, y1, x0, y0
    for y in range(y0, y1 + 1):
        for x in range(x0, x1):
            if px[x, y][3] >= 12:
                bx0, bx1 = min(bx0, x), max(bx1, x)
                by0, by1 = min(by0, y), max(by1, y)
    return (bx0, by0, bx1, by1) if bx1 >= bx0 else None


# ------------------------------------------------------------------ slicing --
def slice_sheet(cfg_path):
    cfg = json.load(open(cfg_path))
    cid = cfg["id"]
    src = cfg["src"] if os.path.isabs(cfg["src"]) else os.path.join(ROOT, cfg["src"])

    print(f"[{cid}] reading {os.path.basename(src)}")
    sheet = despeckle(load_sheet(src))
    W, H = sheet.size
    px = sheet.load()

    # Some sheets carry non-avatar furniture (a wordmark in a corner, say).
    for ex0, ey0, ex1, ey1 in cfg.get("erase", []):
        for y in range(max(0, ey0), min(H, ey1)):
            for x in range(max(0, ex0), min(W, ex1)):
                px[x, y] = (0, 0, 0, 0)

    cols, rows = cfg["cols"], cfg["rows"]
    grid = cfg.get("grid", {})
    x0 = grid.get("x0", 0)
    y0 = grid.get("y0", 0)
    cw = grid.get("cellW", (W - x0) / cols)
    ch = grid.get("cellH", (H - y0) / rows)

    col_prof = [sum(1 for y in range(H) if px[x, y][3] >= 12) for x in range(W)]
    row_prof = [sum(1 for x in range(W) if px[x, y][3] >= 12) for y in range(H)]
    xs = seams(col_prof, x0, cw, cols, W - 1)
    ys = seams(row_prof, y0, ch, rows, H - 1)

    skip = {tuple(s) for s in cfg.get("skip", [])}
    cells = []
    for r in range(rows):
        for c in range(cols):
            if (r, c) in skip:
                continue
            cells.append([r, c, xs[c], xs[c + 1], ys[r], ys[r + 1]])

    # Label pills are fused to the bottom of each bust. The grid is regular, so
    # trust the row's consensus cut rather than any single cell's detection.
    if cfg.get("labels"):
        for r in range(rows):
            row = [cell for cell in cells if cell[0] == r]
            if not row:
                continue
            cuts = sorted(pill_top(px, cell[2], cell[3], cell[4], cell[5]) for cell in row)
            cut = cuts[len(cuts) // 2] - 4
            for cell in row:
                cell[5] = min(cell[5], cut)

    boxes = []
    for r, c, cx0, cx1, cy0, cy1 in cells:
        box = content_bbox(px, cx0, cx1, cy0, cy1)
        if box:
            boxes.append((r, c, cy0, box))
    if not boxes:
        raise SystemExit(f"[{cid}] no content found — check cols/rows/grid")

    # One shared frame for every variant so they line up in the picker, anchored
    # on the hair line: heads sit at a fixed height, but how much of the bust
    # survives varies. Sizing to the shortest bust keeps every tile full-bleed.
    frame_w = max(b[2] - b[0] for *_, b in boxes) + 2
    frame_h = min(b[3] - b[1] for *_, b in boxes) + 1
    print(f"[{cid}] {len(boxes)} variants, uniform frame {frame_w}x{frame_h}")

    out_dir = os.path.join(ASSETS, cid)
    for stale in (os.listdir(out_dir) if os.path.isdir(out_dir) else []):
        os.remove(os.path.join(out_dir, stale))
    os.makedirs(out_dir, exist_ok=True)

    boxes.sort(key=lambda t: (t[0], t[1]))
    for i, (_, _, band_top, (bx0, by0, bx1, by1)) in enumerate(boxes):
        fx = (bx0 + bx1) // 2 - frame_w // 2                # centre horizontally
        top = max(by0, band_top)                            # never reach into the row above
        cell = Image.new("RGBA", (frame_w, frame_h), (0, 0, 0, 0))
        cell.paste(sheet.crop((fx, top, fx + frame_w, top + frame_h)), (0, 0))
        cell.save(os.path.join(out_dir, f"{i + 1:02d}.png"))
        big = cell.resize((frame_w * 2, frame_h * 2), Image.LANCZOS)
        big = big.filter(ImageFilter.UnsharpMask(**RETINA_SHARPEN))
        big.save(os.path.join(out_dir, f"{i + 1:02d}@2x.png"))

    cfg["_frame"] = [frame_w, frame_h]
    return cfg


# ----------------------------------------------------------------- manifest --
def rebuild_manifest(frames):
    """characters.js, not .json — the picker has to run straight off file://."""
    chars = []
    for f in sorted(os.listdir(SHEETS)):
        if not f.endswith(".json"):
            continue
        cfg = json.load(open(os.path.join(SHEETS, f)))
        d = os.path.join(ASSETS, cfg["id"])
        files = sorted(x for x in os.listdir(d)
                       if x.endswith(".png") and "@2x" not in x) if os.path.isdir(d) else []
        # `sourceLabels` is deliberately not read here: char-01's sheet captions
        # were skin-tone descriptors, kept as a record but never shown.
        names = cfg.get("variants") or []
        chars.append({
            "id": cfg["id"],
            "name": cfg["name"],
            "tagline": cfg.get("tagline", ""),
            # Archetype names read as "<username>, the Outlier"; proper names
            # like "Agent Ic" need "playing as" instead.
            "proper": bool(cfg.get("proper")),
            "default": cfg.get("default", 1),
            # 1x frame size, so the picker can cap the preview at life size
            # without waiting on an image to load.
            "frame": frames.get(cfg["id"]) or (
                list(Image.open(os.path.join(d, files[0])).size) if files else None),
            # Only sheets that ship real captions get them shown; the rest are
            # picked by eye, and "Look 07" under every tile is just noise.
            "captions": bool(names),
            "variants": [{"file": f"assets/{cfg['id']}/{fn}",
                          "file2x": f"assets/{cfg['id']}/{fn[:-4]}@2x.png",
                          "name": names[i] if i < len(names) else f"Look {i + 1}"}
                         for i, fn in enumerate(files)],
        })
    chars.sort(key=lambda c: c["id"])
    with open(os.path.join(ROOT, "characters.js"), "w") as fh:
        fh.write("// Generated by tools/slice_sheet.py — do not edit by hand.\n")
        fh.write("window.CHARACTERS = " + json.dumps(chars, indent=2) + ";\n")
    print(f"characters.js rebuilt: {len(chars)} character(s), "
          f"{sum(len(c['variants']) for c in chars)} variants")


if __name__ == "__main__":
    targets = sys.argv[1:] or [os.path.join(SHEETS, f)
                               for f in sorted(os.listdir(SHEETS)) if f.endswith(".json")]
    frames = {}
    for t in targets:
        cfg = slice_sheet(t)
        frames[cfg["id"]] = cfg["_frame"]
    rebuild_manifest(frames)
