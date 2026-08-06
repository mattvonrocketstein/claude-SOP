#!/usr/bin/env python3
"""PreToolUse gate: IsolatedTree write-ownership (codename `iso`).

Blocks the first mutation into an iso-tree this session did not create, since a
tree it does not own is stale, WIP, or foreign, and its state is unknown.
Ownership comes from the manifest csop-gate-bashverb stamps. Reads are never
gated. Fail-open; escape hatch CSOP_ISO=off.
"""
import os
import re
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402

_ISO = disciplines.IsoTree
DISCIPLINE = _ISO.codename
_DIR = _ISO.get("home")
_MANIFEST = "iso-trees.json"


def _tree_name(text):
    i = (text or "").find(_DIR)
    if i < 0:
        return None
    rest = text[i + len(_DIR):].lstrip("/")
    seg = re.split(r"[\s/'\";|&>()]", rest, maxsplit=1)[0]
    return seg or None


def _owned(name, event):
    try:
        data = json.load(open(csop.state_path(_MANIFEST)))
    except Exception:
        return False
    entry = data.get(name) or {}
    return entry.get("session") == csop.session_id(event)


def main():
    event = csop.load_event()
    if not csop.is_active(DISCIPLINE) or csop.escaped(DISCIPLINE):
        csop.allow()
    tool = event.get("tool_name", "")
    ti = event.get("tool_input", {}) or {}
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        name = _tree_name(ti.get("file_path", "") or ti.get("notebook_path", ""))
    elif tool == "Bash":
        cmd = ti.get("command", "") or ""
        name = _tree_name(cmd) if csop.mutates_files(cmd) else None
    else:
        name = None
    if not name or _owned(name, event):
        csop.allow()
    csop.block(
        "CSOP[iso] blocked: iso-tree `{0}` was not created fresh by this session "
        "-- it is stale, WIP, or foreign, and its state is unknown. Do not begin "
        "work by reusing it; start a new worktree: `git worktree add {1}<new> "
        "<clean-base>`. Escape hatch: prefix `CSOP_ISO=off`.".format(name, _DIR))


if __name__ == "__main__":
    main()
