# Recipes

A static, offline-capable browser for the recipe collection in my Obsidian
vault. The markdown notes stay the source of truth; this repo holds a generated
JSON bundle and a small vanilla-JS app that reads it.

Live at **https://erikhicks.github.io/recipes-vault/**

Every path in the app is relative, so it serves correctly from the project
subpath a non-`username.github.io` repo gets, and the local checkout can live
anywhere under any folder name.

## Setup

Once per machine, point the tools at the vault:

```powershell
copy .env.example .env      # then edit RECIPE_VAULT
```

`.env` is gitignored, so local paths never reach the repo. A real environment
variable of the same name overrides the file, which is handy for a one-off run
against a different vault.

## Adding recipes

Clip and process a recipe in Obsidian as usual, then:

```powershell
.\tools\sync.ps1
```

That re-parses the vault, rewrites `data/recipes.json`, commits with a message
describing what changed (`Add 2 recipes: Beef Birria, Khao Soi Soup`), and
pushes. GitHub Pages redeploys from the push.

Useful variations:

```powershell
.\tools\sync.ps1 -Check                    # parse and report, write nothing
.\tools\sync.ps1 -NoPush                   # build and commit, push later
.\tools\sync.ps1 -Vault <path-to-vault>    # a vault somewhere else
py tools\build.py --check                  # the parser on its own
```

`build.py` prints anything that looks off — a recipe with no ingredients, no
method steps, or no summary, and any `Pairs Well With` link pointing at a note
that doesn't exist. Those are usually real gaps in the vault rather than parser
failures, but they're worth a look.

The vault path is resolved in that order: `--vault`, then a `RECIPE_VAULT`
environment variable, then `RECIPE_VAULT` in `.env`. If none is set, the script
says so and tells you how to fix it.

## Running it locally

```powershell
py -m http.server 8765
```

Then open <http://127.0.0.1:8765/>. It has to be served over HTTP —
`file://` blocks the `fetch` that loads the recipe data.

With the server up, <http://127.0.0.1:8765/tools/smoke.html> drives the real app
in an iframe and checks the fiddly parts: quantity scaling, struck-out steps
surviving a reload, tag jumps, filter and search composing, shuffle, and service
worker registration. Worth a look after touching `app.js`.

## How it fits together

```
index.html            markup shell
assets/style.css      all styling, both themes
assets/app.js         the whole app: routing, search, filters, cook mode
assets/icons.svg      one sprite of the hand-drawn icons
data/recipes.json     generated — the only thing that changes most commits
sw.js                 service worker; VERSION is stamped by build.py
.env.example          template for the local paths; copy to .env
tools/build.py        vault -> JSON
tools/envfile.py      tiny .env reader (no dependency needed)
tools/sync.ps1        build, commit, push
tools/smoke.html      browser smoke test
tools/make_icons.py   rebuild the sprite (needs ICON_SOURCE; rarely run)
tools/make_pwa_icons.py  rebuild the app icons (only if the palette changes)
```

No build step for the site itself and no dependencies — not a Node project, no
lockfile, nothing to keep patched. `build.py` is Python stdlib only.

The whole collection is one 260 KB JSON file (about 60 KB over the wire), so
the app loads it once and does all searching and filtering in memory. That's
the right trade until the vault is several times larger; past that, split the
bundle into an index plus per-recipe files.

### Parsing

The vault is consistent enough to parse structurally: a tag line, `## Summary`
with a bolded times line, `## Shopping List`, `## Instructions`, and whatever
optional sections a clipping brought with it. Everything the parser doesn't
recognise is kept verbatim as markdown and rendered as prose, so a clipping
with unusual sections loses nothing.

Two deliberate liberties:

- **Ingredient amounts are split from names** (`Soy sauce – 100 ml`) so the
  amounts can line up in a column. Three separator styles and a leading-quantity
  form are handled; anything unrecognised is left as one string.
- **The "An AI-generated recipe (Claude, not clipped from the web)." sentence
  is dropped from summaries.** All 50 Med-Keto notes open with it, the
  `ai written` tag already says it, and it made every card read the same. Only
  the display copy is affected — the vault keeps the sentence.

### Scaling

The servings stepper multiplies **only the leading number** of each amount.
`2 cans, 14 oz/414 mL each` doubles the cans and leaves the can size alone, and
anything with a temperature in it is skipped. Scaled values are shown in red so
it's obvious what the app touched. Recipes whose yield isn't a number
(`Scales to the pork — source gives no weight`) don't get a stepper at all.

## Design

Kitchen expo ticket: condensed caps, monospace quantities, thermal-print red,
and receipt-style dot leaders running from each ingredient to its amount. The
vault has no photography, so type and taxonomy carry the whole design. The
hand-drawn icons are the counterweight — a human hand against a machine-printed
ticket.

Two themes: `ink` (default) and `paper`, toggled in the header and remembered.

**Cook mode** enlarges everything, holds the screen awake via the Wake Lock API
where the browser supports it, and lets you strike out ingredients and steps as
you go. Progress is stored per recipe in `localStorage` and survives a reload,
so you can put the phone down mid-recipe.

Filters are OR within a dimension and AND across them — "korean or thai, and
quick". Each chip's count reflects every *other* active filter, so the numbers
never contradict the list. Search, filters, and the open recipe all live in the
URL, so any view can be bookmarked or sent to someone.

## GitHub Pages

Settings → Pages → Source: **Deploy from a branch**, branch `main`, folder
`/ (root)`. Nothing else to configure; there's no build to run.

## Credits

- Icons: [Hand-drawn cooking icons](https://goodstuffnononsense.com/) by Good
  Stuff No Nonsense, CC0. Recoloured and packed into a sprite by
  `tools/make_icons.py`.
- Typefaces: Barlow and Barlow Condensed (Jeremy Tribby), DM Mono (Colophon
  Foundry), both SIL Open Font License 1.1. Self-hosted, latin subset, so the
  app works offline.
