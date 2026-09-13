#!/usr/bin/env python3
"""Fold the hand-drawn cooking icons into one recolorable SVG sprite.

    py tools/make_icons.py [path/to/outline/SVG]

The source folder comes from the argument, else ICON_SOURCE in the environment
or .env (see .env.example).

The source icons are CC0 (Good Stuff No Nonsense) and ship as filled paths in a
fixed near-black. We strip that fill so each symbol inherits `currentColor`, and
emit assets/icons.svg as <symbol> elements keyed by the name the app asks for.
Re-run only when the icon set changes; the sprite is committed.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import envfile  # noqa: E402  (needs the path above when run as a script)

# app name -> source filename. Course and protein come straight from the vault's
# own #type/ and #protein/ tag values, so the taxonomy picks the picture.
ICONS = {
    "course-main": "meal", "course-side": "pot", "course-salad": "salad",
    "course-sauce": "jar-of-jam", "course-soup": "soup", "course-appetizer": "taco",
    "course-breakfast": "fried-egg", "course-bread": "bread",
    "course-beverage": "drink", "course-tool": "whisk",
    "protein-beef": "steak", "protein-chicken": "fried-turkey",
    "protein-pork": "sausage", "protein-lamb": "meet-haunch",
    "protein-seafood": "fish", "protein-vegetarian": "carrot",
    "shuffle": "cooking", "cook": "round-basting-cover", "list": "to-do",
    "basket": "shopping-basket", "book": "cook-book", "salt": "salt",
}

# The pack has no UI glyphs, so these are drawn here to sit beside it: stroked
# rather than filled, but tilted and wobbled to match the pack's hand. Stroke
# attributes live on the <g>, so they still take `currentColor` from the page.
HAND = ('fill="none" stroke="currentColor" stroke-width="2.5" '
        'stroke-linecap="round" stroke-linejoin="round"')
CUSTOM = {
    "print": '<g %s transform="rotate(-10 32 32)">'
        '<path d="M20.6 24.1c.3-4.1-.2-8.3.6-12.1.2-1.2 1.1-1.6 2.4-1.7 5.6-.1 11.1.6 16.7.3 1.4 0 2.2.6 2.4 2 .5 3.6.2 7.4.6 11.1"/>'
        '<path d="M18.3 44.9c-1.9.1-3.8.4-5.2-.2-1.3-.6-1.3-2.1-1.4-3.6-.3-4.6-.7-9.4-.2-13.9.2-2 1.1-3.1 3.2-3.3 12.3-.7 24.1-.9 36.1-.4 1.9.1 2.6 1.4 2.8 3.1.4 4.8.8 9.7.3 14.4-.2 1.6-1.1 2.3-2.7 2.4l-5.5.3"/>'
        '<path d="M19.1 37.3c.6-.2 1.3-.1 1.9-.1 7.9-.4 15.9-.7 23.8-.8"/>'
        '<path d="M20 37.2c-.6 5.4-1.4 10.8-.7 16.2.2 1.2 1 1.6 2.2 1.6 7.5.2 14.7-.4 22.1-.5 1.2 0 1.8-.8 1.8-2 .1-5.2-.4-10.3-.8-15.4"/>'
        '<path d="M24.9 43.1c4.6-.3 9.2-.5 13.8-.4M25.2 48.3c3-.2 6-.3 8.9-.1"/>'
        '<path d="M45.1 29.6c.9-.3 1.7.4 1.6 1.3-.1.8-1.1 1.2-1.7.6-.6-.5-.5-1.6.1-1.9z"/>'
        '</g>' % HAND,
    "share": '<g %s transform="rotate(8 32 32)">'
        '<path d="M24.8 27.4c-2.3 0-4.8-.4-6.9.4-1.5.6-1.8 2.2-1.9 3.7-.3 6.1-.6 12.3.3 18.3.3 2 1.6 3.2 3.6 3.3 8.6.5 17.3.3 25.8-.5 1.8-.2 2.5-1.5 2.6-3.2.3-6.2.3-12.4-.3-18.5-.2-1.9-1.2-3-3.1-3.1l-5.6-.2"/>'
        '<path d="M32.4 40.2c-.8-9.8-.5-19.7-.1-29.6"/>'
        '<path d="M23.9 18.6c2.6-2.9 5.5-5.6 8.3-8.4.4-.4.9-.3 1.3.1 2.6 2.6 5.4 5.1 7.7 7.9"/>'
        '</g>' % HAND,
}


def main(src):
    if not os.path.isdir(src):
        sys.exit("Icon source not found: %s" % src)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(here, "assets", "icons.svg")

    symbols, missing = [], []
    for name, filename in ICONS.items():
        path = os.path.join(src, filename + ".svg")
        if not os.path.exists(path):
            missing.append(filename)
            continue
        svg = open(path, encoding="utf-8").read()
        view = re.search(r'viewBox="([^"]+)"', svg)
        body = re.sub(r"^.*?<svg[^>]*>", "", svg, flags=re.S)
        body = re.sub(r"</svg>\s*$", "", body, flags=re.S)
        body = re.sub(r'\s*fill="#[0-9a-fA-F]{3,8}"', "", body)   # inherit currentColor
        symbols.append('<symbol id="i-%s" viewBox="%s">%s</symbol>'
                       % (name, view.group(1) if view else "0 0 64 64", body.strip()))
    for name, body in CUSTOM.items():
        symbols.append('<symbol id="i-%s" viewBox="0 0 64 64">%s</symbol>' % (name, body))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    open(out_path, "w", encoding="utf-8", newline="\n").write(
        '<svg xmlns="http://www.w3.org/2000/svg" style="display:none" '
        'aria-hidden="true"><!-- Hand-drawn cooking icons, CC0. -->'
        + "".join(symbols) + "</svg>\n")

    print("wrote %s (%d symbols, %.1f KB)"
          % (out_path, len(symbols), os.path.getsize(out_path) / 1024))
    if missing:
        print("  missing from source pack: " + ", ".join(missing))


if __name__ == "__main__":
    envfile.load_env()
    main(sys.argv[1] if len(sys.argv) > 1 else envfile.require(
        "ICON_SOURCE", "it should point at the icon pack's outline/SVG folder",
        r"C:\Path\To\hand-drawn-cooking-icons\outline\SVG"))
