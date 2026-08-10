#!/usr/bin/env python3
"""Draw the home-screen icons: the thermal-red order tag from the header rail.

    py tools/make_pwa_icons.py

Pure stdlib (zlib + struct write the PNGs), rendered at 4x and downsampled so
the diagonal edges come out smooth. Re-run only if the palette changes.
"""

import os
import struct
import sys
import zlib

INK = (0x16, 0x13, 0x0F)
THERMAL = (0xE8, 0x41, 0x2C)
SS = 4                      # supersampling factor


def write_png(path, width, height, rows):
    raw = b"".join(b"\x00" + bytes(v for px in row for v in px) for row in rows)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)))
        fh.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        fh.write(chunk(b"IEND", b""))


def in_tag(x, y, size, scale):
    """The header-rail mark: a rectangle ending in a downward point."""
    half_w, top, shoulder, tip = 0.155 * scale, 0.5 - 0.34 * scale, \
        0.5 + 0.16 * scale, 0.5 + 0.34 * scale
    u, v = x / size - 0.5, y / size

    if abs(u) > half_w or v < top or v > tip:
        return None
    if v > shoulder:                      # inside the converging point
        t = (v - shoulder) / (tip - shoulder)
        if abs(u) > half_w * (1 - t):
            return None
    # Two ink rules across the face, uneven so they read as lines of text
    # rather than an equals sign.
    for line, width in ((0.28, 0.66), (0.44, 0.40)):
        band = top + (shoulder - top) * line
        if band <= v <= band + 0.030 * scale and -half_w * 0.66 < u < half_w * (
                -0.66 + 2 * width):
            return INK
    return THERMAL


def render(size, scale):
    big = size * SS
    hi = [[in_tag(x + 0.5, y + 0.5, big, scale) or INK for x in range(big)]
          for y in range(big)]
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            r = g = b = 0
            for dy in range(SS):
                for dx in range(SS):
                    px = hi[y * SS + dy][x * SS + dx]
                    r, g, b = r + px[0], g + px[1], b + px[2]
            n = SS * SS
            row.append((r // n, g // n, b // n))
        rows.append(row)
    return rows


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(here, "assets")
    os.makedirs(out, exist_ok=True)

    # Maskable icons get a smaller mark so Android's circular crop can't clip it.
    for name, size, scale in [("icon-180.png", 180, 1.0), ("icon-192.png", 192, 1.0),
                              ("icon-512.png", 512, 1.0),
                              ("icon-512-maskable.png", 512, 0.62)]:
        path = os.path.join(out, name)
        write_png(path, size, size, render(size, scale))
        print("wrote %s (%.1f KB)" % (name, os.path.getsize(path) / 1024))

    hw, top, shoulder, tip = 0.155, 0.16, 0.66, 0.84
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" fill="#16130F"/>'
        '<path fill="#E8412C" d="M%.1f %.1f H%.1f V%.1f L32 %.1f L%.1f %.1f Z"/>'
        '<rect x="%.1f" y="%.1f" width="%.1f" height="2.2" fill="#16130F"/>'
        '<rect x="%.1f" y="%.1f" width="%.1f" height="2.2" fill="#16130F"/>'
        "</svg>\n"
    ) % (
        (0.5 - hw) * 64, top * 64, (0.5 + hw) * 64, shoulder * 64, tip * 64,
        (0.5 - hw) * 64, shoulder * 64,
        (0.5 - hw * 0.66) * 64, (top + (shoulder - top) * 0.28) * 64, hw * 1.32 * 64,
        (0.5 - hw * 0.66) * 64, (top + (shoulder - top) * 0.44) * 64, hw * 0.80 * 64,
    )
    open(os.path.join(out, "favicon.svg"), "w", encoding="utf-8",
         newline="\n").write(svg)
    print("wrote favicon.svg")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    main()
