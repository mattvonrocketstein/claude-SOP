#!/usr/bin/env python3
"""PreToolUse gate: IsolatedTree worktree creation (codename `iso`).

Blocks a worktree added outside the crash-safe iso dir, and stamps one added
inside it into a session-owned manifest, so csop-gate-isowrite can later tell a
freshly created tree from a reused stale one. Fail-open; hatch CSOP_ISO=off.
"""
import os
import re
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402

_ISO = disciplines.IsoTree
DISCIPLINE = _ISO.codename                                 # "iso"
_DIR = _ISO.get("home")                                    # project-overridable
_MANIFEST = "iso-trees.json"
_VERB = re.compile(r"\bgit\b[^|;&]*\bworktree\s+add\b")
_REQUIRED = re.compile(re.escape(_DIR))
_MSG = ("CSOP[iso] blocked: `git worktree add` must target the crash-safe iso "
        "dir ({0}<name>), never /tmp. Escape hatch: prefix `CSOP_ISO=off`.".format(_DIR))


def _tree_name(text):
    i = (text or "").find(_DIR)
    if i < 0:
        return None
    rest = text[i + len(_DIR):].lstrip("/")
    seg = re.split(r"[\s/'\";|&>()]", rest, maxsplit=1)[0]
    return seg or None


def _stamp(name, event):
    proj = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    if os.path.exists(os.path.join(proj, _DIR, name)):
        return                             # existing path: a reuse, not a fresh create
    path = csop.state_path(_MANIFEST)
    try:
        data = json.load(open(path))
    except Exception:
        data = {}
    data[name] = {"session": csop.session_id(event)}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def main():
    event = csop.load_event()
    if event.get("tool_name") != "Bash":
        csop.allow()
    if not csop.is_active(DISCIPLINE) or csop.escaped(DISCIPLINE):
        csop.allow()                       # discipline off -> no enforcement
    cmd = (event.get("tool_input", {}) or {}).get("command", "") or ""
    if not _VERB.search(cmd):
        csop.allow()
    if not _REQUIRED.search(cmd):
        csop.block(_MSG)
    name = _tree_name(cmd)
    if name:
        _stamp(name, event)
    csop.allow()


if __name__ == "__main__":
    main()
