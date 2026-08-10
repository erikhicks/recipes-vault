#!/usr/bin/env python3
"""Turn the Obsidian recipe vault into the single JSON bundle the site loads.

    py tools/build.py                        # vault path from .env
    py tools/build.py --vault <path>         # or point it somewhere else
    py tools/build.py --check                # parse and report, write nothing

The vault path is resolved from --vault, then the RECIPE_VAULT environment
variable, then RECIPE_VAULT in .env (see .env.example).

Stdlib only, so there's nothing to install and nothing to keep patched.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import envfile  # noqa: E402  (needs the path above when run as a script)

# Tag prefixes map onto the filter groups the UI renders, in this order.
PREFIX_GROUPS = [("cuisine", "cuisine"), ("type", "course"),
                 ("protein", "protein"), ("diet", "diet")]
BARE_GROUP = {
    "mealprep": "method", "quick": "method", "advanced": "method",
    "loweffort": "method", "fermented": "method", "slowcook": "method",
    "batch": "method", "single": "method", "scalable": "method",
    "aigenerated": "method",
}

UNITS = (r"tsp|teaspoons?|tbsp|tablespoons?|cups?|g|grams?|kg|ml|l|liters?|litres?|"
         r"oz|lbs?|pounds?|cans?|cloves?|slices?|sprigs?|bunch(?:es)?|sticks?|"
         r"pinch(?:es)?|dash(?:es)?|heads?|stalks?|pieces?|quarts?|pints?|"
         r"inch(?:es)?|cm|packets?|jars?|bottles?|ears?|fillets?|links?")
NUM = r"(?:\d+(?:[.,]\d+)?|[\u00bc\u00bd\u00be\u2153\u2154\u215b\u215c\u215d\u215e])"
QTY_LEAD = re.compile(
    r"^(" + NUM + r"(?:\s*(?:-|\u2013|\u2014|to|/)\s*" + NUM + r")?"
    r"(?:\s*(?:" + UNITS + r")\b\.?)?)\s+(\S.*)$", re.I)

SEPARATORS = [" \u2013 ", " \u2014 ", " - ", "\u2013 ", "\u2014 "]
SECTION_RE = re.compile(r"^##\s+(.*\S)\s*$")
SUBSECTION_RE = re.compile(r"^###\s+(.*\S)\s*$")
CHECKBOX_RE = re.compile(r"^[-*]\s+\[[ xX]\]\s*(.*)$")
NUMBERED_RE = re.compile(r"^(\d+)\.\s+(.*)$")
BULLET_RE = re.compile(r"^[-*]\s+(?!\[[ xX]\])(.*)$")
STEPNAME_RE = re.compile(r"^\*\*(.+?)\*\*\s*[:\u2013\u2014-]?\s*(.*)$")
TAGLINE_RE = re.compile(r"^#[A-Za-z][\w/-]*(\s+#[A-Za-z][\w/-]*)*\s*$")
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:\|([^\]]+))?\]\]")
# Every note in AI Generated Med-Keto opens with the same disclosure sentence.
# The #aigenerated tag is rendered on the card, so the sentence is redundant in
# the app and makes 50 summaries start identically. Dropped for display only —
# the vault keeps it.
BOILERPLATE_RE = re.compile(
    r"^An AI-generated recipe \(Claude, not clipped from the web\)\.\s*", re.I)
TABLEROW_RE = re.compile(r"^\|(.+)\|\s*$")
YIELD_RANGE_RE = re.compile(NUM + r"\s*(?:-|\u2013|to)\s*(\d+)")


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", text) or "untitled"


def strip_inline(text):
    """Plain text for the search index — drop the markup, keep the words."""
    text = WIKILINK_RE.sub(lambda m: m.group(2) or m.group(1), text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return re.sub(r"[*_`#>]", "", text).strip()


def split_sections(lines):
    """[(heading|None, [line, ...]), ...] — leading lines land under None."""
    out, heading, buf = [], None, []
    for line in lines:
        m = SECTION_RE.match(line)
        if m:
            out.append((heading, buf))
            heading, buf = m.group(1), []
        else:
            buf.append(line)
    out.append((heading, buf))
    return [(h, b) for h, b in out if h is not None or any(x.strip() for x in b)]


def trim(lines):
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def split_amount(raw):
    """'Soy sauce - 100 ml' -> ('Soy sauce', '100 ml'). Best effort, never lossy."""
    raw = raw.strip().rstrip(".")
    for sep in SEPARATORS:
        if sep in raw:
            name, _, amount = raw.partition(sep)
            if name.strip() and amount.strip():
                return name.strip(), amount.strip()
    m = QTY_LEAD.match(raw)
    if m:
        return m.group(2).strip(), m.group(1).strip()
    return raw, ""


def parse_times(text):
    """The '**Prep Time:** X | **Cook Time:** Y | **Yield:** Z' line."""
    times = {}
    for label, value in re.findall(r"\*\*([^*:]+):?\*\*:?\s*([^|]+)", text):
        key = label.strip().lower().replace(" time", "").replace(" ", "")
        times[key] = value.strip().rstrip("|").strip()
    return times


def parse_servings(yield_text):
    """A number the scaler can multiply, or None when the yield isn't countable."""
    if not yield_text:
        return None, None
    m = re.search(r"(\d+)\s*(?:-|\u2013|to)\s*(\d+)", yield_text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"\b(\d+)\b", yield_text)
    if m:
        n = int(m.group(1))
        return (n, n) if 0 < n <= 200 else (None, None)
    return None, None


def parse_shopping(lines):
    """Checkbox lists and the occasional markdown table both become items."""
    groups, section, items = [], None, []

    def flush():
        if items:
            groups.append({"section": section, "items": list(items)})
            items.clear()

    in_table = False
    for line in lines:
        m = SUBSECTION_RE.match(line)
        if m:
            flush()
            section, in_table = m.group(1), False
            continue
        m = CHECKBOX_RE.match(line)
        if m and m.group(1).strip():
            name, amount = split_amount(strip_inline(m.group(1)))
            items.append({"name": name, "amount": amount})
            continue
        m = TABLEROW_RE.match(line)
        if m:
            cells = [c.strip() for c in m.group(1).split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                in_table = True          # the header rule; the header row precedes it
                if items:
                    items.pop()          # drop the column titles we just captured
                continue
            if len(cells) >= 2:
                items.append({"name": strip_inline(cells[0]),
                              "amount": strip_inline(cells[1])})
            continue
        if in_table and not line.strip():
            in_table = False
    flush()
    return groups


def parse_steps(lines):
    """Numbered (or bulleted) steps, optionally grouped under ### subsections."""
    groups, section, steps = [], None, []

    def flush():
        if steps:
            groups.append({"section": section, "steps": list(steps)})
            steps.clear()

    for line in lines:
        m = SUBSECTION_RE.match(line)
        if m:
            flush()
            section = m.group(1)
            continue
        m = NUMBERED_RE.match(line) or BULLET_RE.match(line)
        if m and line.strip():
            body = (m.group(2) if m.re is NUMBERED_RE else m.group(1)).strip()
            name = ""
            sm = STEPNAME_RE.match(body)
            if sm and len(sm.group(1)) <= 60:
                name, body = sm.group(1).strip().rstrip(":"), sm.group(2).strip()
            steps.append({"name": name, "text": strip_inline(body),
                          "md": body, "sub": []})
            continue
        if steps and line.strip():
            # A continuation line or nested bullet belonging to the step above.
            steps[-1]["sub"].append(strip_inline(line.strip().lstrip("-*").strip()))
    flush()
    return groups


def parse_pairs(lines):
    """'- [[Recipe]] — why it works' rows."""
    out = []
    for line in lines:
        m = BULLET_RE.match(line)
        if not m:
            continue
        link = WIKILINK_RE.search(m.group(1))
        if not link:
            continue
        rest = m.group(1)[link.end():].strip()
        out.append({"title": link.group(1).strip(),
                    "note": strip_inline(re.sub(r"^[\u2013\u2014-]\s*", "", rest))})
    return out


def parse_recipe(path, vault):
    rel = os.path.relpath(path, vault).replace("\\", "/")
    raw = open(path, encoding="utf-8").read().replace("\r\n", "\n")
    lines = raw.split("\n")

    tags = []
    if lines and TAGLINE_RE.match(lines[0].strip()):
        tags = [t.lstrip("#") for t in lines[0].split()]
        lines = lines[1:]
    if not any(t.startswith("type/") for t in tags):
        return None                      # hub note, folder index, or unprocessed clip

    title = os.path.splitext(os.path.basename(path))[0]
    folder = os.path.dirname(rel)

    summary, times, shopping, steps, pairs, extras = "", {}, [], [], [], []
    for heading, body in split_sections(lines):
        body = trim(list(body))
        key = (heading or "").strip().lower()
        if key in ("summary", ""):
            para = []
            for line in body:
                if "**" in line and re.search(r"\b(time|yield|serves|makes)\b", line, re.I):
                    times.update(parse_times(line))
                elif line.strip() == "---":
                    continue
                else:
                    para.append(line)
            text = BOILERPLATE_RE.sub(
                "", strip_inline(" ".join(x.strip() for x in para if x.strip())))
            summary = (summary + " " + text).strip() if summary else text
        elif key == "shopping list":
            shopping = parse_shopping(body)
        elif key == "instructions":
            steps = parse_steps(body)
        elif key == "pairs well with":
            pairs = parse_pairs(body)
        elif heading:
            md = "\n".join(x for x in body if x.strip() != "---").strip()
            if md:
                extras.append({"heading": heading, "md": md})

    lo, hi = parse_servings(times.get("yield", ""))
    facets = {}
    for tag in tags:
        prefix, _, value = tag.partition("/")
        group = next((g for p, g in PREFIX_GROUPS if p == prefix), None) if value \
            else BARE_GROUP.get(tag)
        if group:
            facets.setdefault(group, []).append(value or tag)

    return {
        "slug": slugify(title),
        "title": title,
        "folder": folder,
        "tags": tags,
        "facets": facets,
        "summary": summary,
        "times": times,
        "servings": lo,
        "servingsMax": hi,
        "shopping": shopping,
        "steps": steps,
        "pairs": pairs,
        "extras": extras,
        "links": sorted({m.group(1).strip() for m in WIKILINK_RE.finditer(raw)}),
    }


def parse_cuisine_hub(path):
    raw = open(path, encoding="utf-8").read().replace("\r\n", "\n")
    name = os.path.splitext(os.path.basename(path))[0]
    notes = []
    for heading, body in split_sections(raw.split("\n")):
        key = (heading or "").strip().lower()
        if key in ("notes", "serving notes", "pairing notes", "storage notes"):
            notes.append(strip_inline(" ".join(x.strip() for x in body if x.strip())))
    return {"slug": name.lower(), "name": name, "notes": " ".join(notes).strip()}


SHELL_FILES = ["index.html", "assets/style.css", "assets/app.js",
               "assets/fonts.css", "assets/icons.svg", "manifest.webmanifest"]


def stamp_service_worker(root):
    """Point the shell cache at a hash of the shell, so deploys self-invalidate."""
    sw_path = os.path.join(root, "sw.js")
    if not os.path.exists(sw_path):
        return None
    digest = hashlib.sha256()
    for rel in SHELL_FILES:
        path = os.path.join(root, rel.replace("/", os.sep))
        if os.path.exists(path):
            digest.update(open(path, "rb").read())
    version = digest.hexdigest()[:12]

    source = open(sw_path, encoding="utf-8").read()
    updated = re.sub(r'const VERSION = "[^"]*";',
                     'const VERSION = "%s";' % version, source, count=1)
    if updated != source:
        open(sw_path, "w", encoding="utf-8", newline="\n").write(updated)
    return version


def unchanged(bundle, out_path):
    """True when the only difference from the file on disk is the timestamp."""
    if not os.path.exists(out_path):
        return False
    try:
        with open(out_path, encoding="utf-8") as fh:
            previous = json.load(fh)
    except ValueError:
        return False
    strip = lambda b: {k: v for k, v in b.items() if k != "generated"}  # noqa: E731
    return strip(previous) == strip(bundle)


def write_commit_message(bundle, out_path, root):
    """Diff against the last build so sync.ps1 can commit something meaningful."""
    def names(titles, limit=4):
        titles = sorted(titles)
        if len(titles) <= limit:
            return ": " + ", ".join(titles)
        return ": " + ", ".join(titles[:limit]) + " and %d more" % (len(titles) - limit)

    previous = {}
    if os.path.exists(out_path):
        try:
            with open(out_path, encoding="utf-8") as fh:
                previous = {r["slug"]: r for r in json.load(fh).get("recipes", [])}
        except (ValueError, KeyError):
            previous = {}

    current = {r["slug"]: r for r in bundle["recipes"]}
    added = [current[s]["title"] for s in current.keys() - previous.keys()]
    removed = [previous[s]["title"] for s in previous.keys() - current.keys()]
    changed = [current[s]["title"] for s in current.keys() & previous.keys()
               if {k: v for k, v in current[s].items() if k != "id"}
               != {k: v for k, v in previous[s].items() if k != "id"}]

    if added and not removed and not changed:
        subject = "Add %d recipe%s%s" % (len(added), "" if len(added) == 1 else "s",
                                         names(added))
    elif changed and not added and not removed:
        subject = "Update %d recipe%s%s" % (len(changed), "" if len(changed) == 1 else "s",
                                            names(changed))
    elif added or removed or changed:
        parts = []
        if added:
            parts.append("%d added" % len(added))
        if changed:
            parts.append("%d updated" % len(changed))
        if removed:
            parts.append("%d removed" % len(removed))
        subject = "Sync recipes (%s)" % ", ".join(parts)
    else:
        subject = "Rebuild site (no recipe changes)"

    body = []
    for label, titles in (("Added", added), ("Updated", changed), ("Removed", removed)):
        for title in sorted(titles):
            body.append("%s: %s" % (label, title))

    with open(os.path.join(root, ".build-message"), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write(subject + ("\n\n" + "\n".join(body) if body else "") + "\n")
    print(subject)


def build(vault, out_path, root, check_only=False):
    if not os.path.isdir(vault):
        sys.exit("Vault not found: %s\n"
                 "Check RECIPE_VAULT in .env, or pass --vault." % vault)

    recipes, skipped = [], []
    # Not sorted(os.walk(...)) — that drains the generator before the dirs[:]
    # pruning below can take effect, and Cuisines gets walked anyway.
    for dirpath, dirs, files in os.walk(vault):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d != "Cuisines")
        for fn in sorted(files):
            if not fn.endswith(".md"):
                continue
            path = os.path.join(dirpath, fn)
            # A note named after its own folder is that folder's index, not a recipe.
            if os.path.splitext(fn)[0] == os.path.basename(dirpath):
                continue
            try:
                parsed = parse_recipe(path, vault)
            except Exception as exc:                      # noqa: BLE001
                skipped.append((fn, "parse error: %s" % exc))
                continue
            if parsed is None:
                skipped.append((fn, "no #type/ tag — unprocessed?"))
            else:
                recipes.append(parsed)

    recipes.sort(key=lambda r: r["title"].lower())
    for i, r in enumerate(recipes, 1):
        r["id"] = i                                        # stable ticket number

    by_title = {r["title"]: r["slug"] for r in recipes}
    unresolved = set()
    for r in recipes:
        for pair in r["pairs"]:
            pair["slug"] = by_title.get(pair["title"])
            if not pair["slug"]:
                unresolved.add("%s -> %s" % (r["title"], pair["title"]))
        r["links"] = [{"title": t, "slug": by_title[t]} for t in r["links"] if t in by_title]

    cuisine_dir = os.path.join(vault, "Cuisines")
    cuisines = [parse_cuisine_hub(os.path.join(cuisine_dir, f))
                for f in sorted(os.listdir(cuisine_dir))
                if f.endswith(".md")] if os.path.isdir(cuisine_dir) else []

    groups = {}
    for r in recipes:
        for group, values in r["facets"].items():
            for v in values:
                groups.setdefault(group, {})
                groups[group][v] = groups[group].get(v, 0) + 1
    facet_index = {g: [{"value": v, "count": c}
                       for v, c in sorted(vals.items(), key=lambda kv: (-kv[1], kv[0]))]
                   for g, vals in groups.items()}

    bundle = {
        "generated": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "count": len(recipes),
        "facets": facet_index,
        "cuisines": cuisines,
        "recipes": recipes,
    }

    ingredient_total = sum(len(g["items"]) for r in recipes for g in r["shopping"])
    step_total = sum(len(g["steps"]) for r in recipes for g in r["steps"])
    print("%d recipes | %d ingredients | %d steps | %d cuisine hubs"
          % (len(recipes), ingredient_total, step_total, len(cuisines)))

    for label, missing in (
        ("no ingredients", [r["title"] for r in recipes if not r["shopping"]]),
        ("no steps", [r["title"] for r in recipes if not r["steps"]]),
        ("no summary", [r["title"] for r in recipes if not r["summary"]]),
    ):
        if missing:
            print("  %s: %s" % (label, ", ".join(missing)))
    if unresolved:
        print("  pairing links with no matching note: " + "; ".join(sorted(unresolved)))
    for fn, why in skipped:
        print("  skipped %s (%s)" % (fn, why))

    if check_only:
        print("--check: nothing written")
        return bundle

    write_commit_message(bundle, out_path, root)

    # `generated` moves on every run, so comparing the whole file would make
    # each build look like a change and defeat sync.ps1's no-op check. Only
    # rewrite when the recipes themselves differ; the timestamp then honestly
    # means "when the data last changed".
    if unchanged(bundle, out_path):
        print("data unchanged, left %s alone" % os.path.basename(out_path))
    else:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(bundle, fh, ensure_ascii=False, separators=(",", ":"))
        print("wrote %s (%.1f KB)" % (out_path, os.path.getsize(out_path) / 1024))

    version = stamp_service_worker(root)
    if version:
        print("service worker cache: shell-%s" % version)
    return bundle


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # recipe titles carry accents
    except AttributeError:
        pass
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    envfile.load_env(here)

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", help="path to the Recipes folder in the vault")
    ap.add_argument("--out", default=os.path.join(here, "data", "recipes.json"))
    ap.add_argument("--check", action="store_true", help="parse and report, write nothing")
    args = ap.parse_args()

    vault = args.vault or envfile.require(
        "RECIPE_VAULT", "it should point at the Recipes folder in your vault",
        r"C:\Path\To\Vault\Recipes")
    build(vault, args.out, here, args.check)
