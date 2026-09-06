#!/usr/bin/env python3
"""
Unwrap a background-removed "SVG" contact sheet into a real RGBA PNG.

The design-tool export isn't vector at all: it's the original raster wrapped in
an <svg>, with a second raster used as a luminance <mask>. Pull both out and
composite them so the sheet arrives with genuine alpha.

    python3 tools/svg_to_rgba.py in.svg out.png
"""
import base64, io, re, sys
from PIL import Image

DATA = re.compile(r'xlink:href="data:image/(?:png|jpeg);base64,([^"]+)"')


def unwrap(svg_path):
    svg = open(svg_path, encoding="utf-8", errors="replace").read()
    blobs = DATA.findall(svg)
    if len(blobs) < 2:
        raise SystemExit(f"{svg_path}: expected a colour image and a mask, found {len(blobs)}")

    # The mask <image> is declared inside <defs><mask>, so it comes first.
    mask = Image.open(io.BytesIO(base64.b64decode(blobs[0]))).convert("L")
    art = Image.open(io.BytesIO(base64.b64decode(blobs[1]))).convert("RGB")
    if mask.size != art.size:
        mask = mask.resize(art.size, Image.LANCZOS)

    out = art.convert("RGBA")
    out.putalpha(mask)
    return out


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    im = unwrap(src)
    im.save(dst)
    print(f"{src} -> {dst}  {im.size[0]}x{im.size[1]}")
