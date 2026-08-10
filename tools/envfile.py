#!/usr/bin/env python3
"""A very small .env reader, so the tools stay dependency-free.

Handles what a .env for this project needs and nothing more: KEY=VALUE lines,
`#` comments, blank lines, an optional `export ` prefix, and optional quotes
around the value. A variable already present in the real environment always
wins, so `$env:RECIPE_VAULT = "..."` overrides the file for one-off runs.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env(root=REPO_ROOT):
    """Read <root>/.env into os.environ without clobbering what's already set."""
    path = os.path.join(root, ".env")
    if not os.path.exists(path):
        return {}

    values = {}
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].lstrip()
            key, sep, value = line.partition("=")
            if not sep:
                print("warning: %s line %d is not KEY=VALUE, skipping"
                      % (path, lineno), file=sys.stderr)
                continue
            key, value = key.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key] = value
            os.environ.setdefault(key, value)
    return values


def require(name, what, example):
    """Fetch a required setting, or exit explaining exactly how to set it."""
    value = os.environ.get(name)
    if value:
        return value
    # Plain ASCII: this goes to stderr, which isn't reconfigured to UTF-8.
    sys.exit(
        "%s is not set - %s.\n\n"
        "Copy .env.example to .env and fill it in:\n"
        "    copy .env.example .env\n\n"
        "then set, for example:\n"
        "    %s=%s\n\n"
        ".env is gitignored, so your local paths stay out of the repo."
        % (name, what, name, example)
    )
