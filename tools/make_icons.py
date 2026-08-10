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
