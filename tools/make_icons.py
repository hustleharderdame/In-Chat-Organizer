#!/usr/bin/env python3
"""
---
node_id: "cos_icon_generator"
node_type: "code"
version: "1.0.0"
status: "active"
single_source: true
tags:
  - "domain/software"
  - "status/active"
  - "tech/python"
parent_node: "[[Master_OS_Hub]]"
linked_nodes:
  - "[[Chat_Root_Organizer_Android]]"
  - "[[Chat_Root_Organizer_Service]]"
---

Icon generator for [[Chat_Root_Organizer_Android]].

Writes the PWA and launcher icons with a pure-Python PNG encoder — no Pillow, no
native deps. That matters: the whole point of this stack is that it runs on a
4GB Moto G under Termux, where `pip install pillow` means compiling.

The glyph is the thing the app *is*: nodes joined by edges.

    run:: python3 tools/make_icons.py
    outputs:: chat_organizer/web/icons/*.png
    owner:: [[Damien_Brock]]
"""

from __future__ import annotations

import math
import pathlib
import struct
import zlib
from typing import List, Sequence, Tuple

OUT_DIR = pathlib.Path(__file__).resolve().parents[1] / "chat_organizer" / "web" / "icons"

RGBA = Tuple[int, int, int, int]
TRANSPARENT: RGBA = (0, 0, 0, 0)
BACKGROUND: RGBA = (21, 25, 34, 255)   # deep slate — reads as "system", not "app"
ACCENT: RGBA = (232, 163, 61, 255)     # amber node fill
EDGE: RGBA = (108, 196, 178, 255)      # teal edges
NODE_RIM: RGBA = (245, 232, 210, 255)

SUPERSAMPLE = 4                     # rendered at 4x, box-filtered down


# --- PNG encoding ------------------------------------------------------------
def write_png(path: pathlib.Path, pixels: Sequence[Sequence[RGBA]]) -> None:
    """Write an RGBA8 PNG. Alpha is not optional: without it the rounded corners
    render as a black square on any light background."""
    height = len(pixels)
    width = len(pixels[0])

    raw = bytearray()
    for row in pixels:
        raw.append(0)  # filter type 0 (None) — icons are small, don't over-engineer
        for r, g, b, a in row:
            raw += bytes((r, g, b, a))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = b"\x89PNG\r\n\x1a\n"
    # colour type 6 == truecolour with alpha
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


# --- drawing -----------------------------------------------------------------
class Canvas:
    def __init__(self, size: int, background: RGBA) -> None:
        self.size = size
        self.px: List[List[RGBA]] = [[background] * size for _ in range(size)]

    def set(self, x: int, y: int, colour: RGBA) -> None:
        if 0 <= x < self.size and 0 <= y < self.size:
            self.px[y][x] = colour

    def disc(self, cx: float, cy: float, radius: float, colour: RGBA) -> None:
        r2 = radius * radius
        for y in range(max(0, int(cy - radius) - 1), min(self.size, int(cy + radius) + 2)):
            for x in range(max(0, int(cx - radius) - 1), min(self.size, int(cx + radius) + 2)):
                if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= r2:
                    self.set(x, y, colour)

    def line(self, x0: float, y0: float, x1: float, y1: float, width: float, colour: RGBA) -> None:
        length = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, int(length * 2))
        for i in range(steps + 1):
            t = i / steps
            self.disc(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, width / 2, colour)

    def rounded_rect(self, inset: float, radius: float, colour: RGBA) -> None:
        lo, hi = inset, self.size - inset
        for y in range(self.size):
            for x in range(self.size):
                px, py = x + 0.5, y + 0.5
                if not (lo <= px <= hi and lo <= py <= hi):
                    continue
                cx = min(max(px, lo + radius), hi - radius)
                cy = min(max(py, lo + radius), hi - radius)
                if (px - cx) ** 2 + (py - cy) ** 2 <= radius * radius:
                    self.set(x, y, colour)

    def downsample(self, factor: int) -> List[List[RGBA]]:
        """Box filter — where the anti-aliasing comes from.

        Colour is averaged *premultiplied* by alpha and then unpremultiplied.
        Averaging straight RGB instead would drag transparent pixels' zeroes
        into the edge colour and fringe every rounded corner with black.
        """
        out_size = self.size // factor
        n = factor * factor
        out: List[List[RGBA]] = []
        for y in range(out_size):
            row: List[RGBA] = []
            for x in range(out_size):
                r = g = b = a = 0
                for dy in range(factor):
                    for dx in range(factor):
                        pr, pg, pb, pa = self.px[y * factor + dy][x * factor + dx]
                        r += pr * pa
                        g += pg * pa
                        b += pb * pa
                        a += pa
                if a == 0:
                    row.append(TRANSPARENT)
                else:
                    row.append((r // a, g // a, b // a, a // n))
            out.append(row)
        return out


def draw_glyph(canvas: Canvas, scale: float, offset: float) -> None:
    """Four nodes and three edges — a root with two children and one cross-link."""
    def point(ux: float, uy: float) -> Tuple[float, float]:
        return (offset + ux * scale, offset + uy * scale)

    root = point(0.5, 0.16)
    left = point(0.17, 0.74)
    right = point(0.83, 0.74)
    mid = point(0.5, 0.50)

    edge_w = scale * 0.055
    canvas.line(*root, *left, edge_w, EDGE)
    canvas.line(*root, *right, edge_w, EDGE)
    canvas.line(*left, *right, edge_w * 0.8, EDGE)

    for centre, radius in ((mid, 0.075), (root, 0.125), (left, 0.105), (right, 0.105)):
        canvas.disc(*centre, scale * (radius + 0.022), BACKGROUND)
        canvas.disc(*centre, scale * radius, NODE_RIM if centre is root else ACCENT)


def render(size: int, *, maskable: bool) -> List[List[RGBA]]:
    """A maskable icon keeps its glyph inside the 80% safe zone Android crops to."""
    big = size * SUPERSAMPLE
    canvas = Canvas(big, BACKGROUND if maskable else TRANSPARENT)

    if maskable:
        # Full bleed: the launcher supplies the mask.
        canvas.rounded_rect(0, 0, BACKGROUND)
        glyph_scale, glyph_offset = big * 0.56, big * 0.22
    else:
        canvas.rounded_rect(big * 0.06, big * 0.21, BACKGROUND)
        glyph_scale, glyph_offset = big * 0.66, big * 0.17

    draw_glyph(canvas, glyph_scale, glyph_offset)
    return canvas.downsample(SUPERSAMPLE)


def main() -> None:
    targets = [
        ("icon-192.png", 192, False),
        ("icon-512.png", 512, False),
        ("icon-maskable-512.png", 512, True),
    ]
    for name, size, maskable in targets:
        path = OUT_DIR / name
        write_png(path, render(size, maskable=maskable))
        print(f"wrote {path.relative_to(OUT_DIR.parents[2])} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
