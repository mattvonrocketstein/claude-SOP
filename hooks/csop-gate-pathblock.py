#!/usr/bin/env python3
"""PreToolUse gate: Frozen Features (codename `freeze`) -- protected paths + regions.

A tool call touching one of the discipline's `frozen` entries is stopped: a whole
path under `no-write` / `no-touch` / `no-restructure`, or a region of a file
matched by `regex` (hard) or described in `prose` (a nudge). Modes, matching, and
`exempt` are in docs/gate-internals.md. Fail-open; escape hatch CSOP_FREEZE=off.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402

_FREEZE = disciplines.FrozenFeatures
DISCIPLINE = _FREEZE.codename

_WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
_READ_TOOLS = ("Read", "Grep", "Glob", "Bash")

_BAD = []                                 # frozen entries dropped as unusable


def _entries():
    default_mode = _FREEZE.get("mode") or "no-write"
    out = []
    for item in _FREEZE.get("frozen") or []:
        if isinstance(item, dict):
            path = item.get("path", "")
            if path:
                out.append({"path": path, "mode": item.get("mode") or default_mode,
                            "why": item.get("why", ""), "use": item.get("use", ""),
                            "regex": item.get("regex", ""), "prose": item.get("prose", ""),
                            "exempt": item.get("exempt") or []})
            else:
                _BAD.append("no `path` key: {0}".format(sorted(item)))
        elif item:
            out.append({"path": item, "mode": default_mode, "why": "", "use": "",
                        "regex": "", "prose": "", "exempt": []})
    return out


def _texts(tool, ti):
    if tool in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit"):
        return (ti.get("file_path", ""), ti.get("notebook_path", ""))
    if tool in ("Grep", "Glob"):
        return (ti.get("path", ""), ti.get("pattern", ""), ti.get("glob", ""))
    if tool == "Bash":
        return (ti.get("command", ""),)
    return ()


def _applies(mode, tool):
    if mode == "no-restructure":
        return False                      # only the destructive-Bash branch gates this mode
    if tool in _WRITE_TOOLS:
        return True
    return mode == "no-touch" and tool in _READ_TOOLS


def _refs(path, text):
    """True if `text` mentions `path` not preceded by a word char, so a fragment
    like `.cmk/` is not matched inside `foo.cmk/`. Falls back to substring."""
    try:
        return re.search(r"(?<!\w)" + re.escape(path), text or "") is not None
    except Exception:
        return bool(path) and path in (text or "")


def _exempt(entry, *texts):
    frags = entry.get("exempt") or []
    return any(x and any(x in t for t in texts if t) for x in frags)


def _read(fpath):
    p = fpath or ""
    if not os.path.isabs(p):
        p = os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()), p)
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return None


def _olds(tool, ti):
    if tool == "Edit":
        return [ti.get("old_string", "") or ""]
    if tool == "MultiEdit":
        return [e.get("old_string", "") or "" for e in (ti.get("edits") or [])]
    return []


def _regex_hit(entry, tool, ti):
    fp = ti.get("file_path", "") or ""
    if not fp or entry["path"] not in fp:
        return False
    content = _read(fp)
    if content is None:
        return False
    try:
        rx = re.compile(entry["regex"], re.DOTALL)
    except Exception:
        return False
    spans = [(m.start(), m.end()) for m in rx.finditer(content)]
    if not spans:
        return False
    if tool == "Write":
        cur = "\x00".join(content[s:e] for s, e in spans)
        nxt = "\x00".join(m.group(0) for m in rx.finditer(ti.get("content", "") or ""))
        return cur != nxt
    for old in _olds(tool, ti):
        if not old:
            continue
        i = content.find(old)
        if i < 0:
            continue
        a, b = i, i + len(old)
        if any(a < e and s < b for s, e in spans):
            return True
    return False


def _prose_hit(entry, ti):
    fp = ti.get("file_path", "") or ""
    return bool(fp) and entry["path"] in fp


def _region_msg(entry):
    parts = ["Frozen Features ({0}): a protected region of `{1}` is off-limits.".format(
        DISCIPLINE, entry["path"])]
    if entry["prose"]:
        parts.append("Region: " + entry["prose"] + ".")
    if entry["why"]:
        parts.append(entry["why"])
    if entry["use"]:
        parts.append("Use `{0}` instead.".format(entry["use"]))
    parts.append("Leave that region unchanged. Escape hatch: CSOP_FREEZE=off.")
    return "\n".join(parts)


def _restructure_msg(entry, verbs):
    parts = ["Frozen Features ({0}): `{1}` must not be restructured by shell "
             "({2}); edit its files in place with the Edit/Write tool instead.".format(
                 DISCIPLINE, entry["path"], "/".join(verbs))]
    if entry["why"]:
        parts.append(entry["why"])
    if entry["use"]:
        parts.append("Use `{0}` instead.".format(entry["use"]))
    parts.append("A non-liftable rule belongs in the harness deny-list; this hook "
                 "still lifts with CSOP_FREEZE=off.")
    return "\n".join(parts)


def _path_msg(entry):
    kind = ("a no-touch path (reads and writes both trap)"
            if entry["mode"] == "no-touch" else "a frozen path (do not modify)")
    parts = ["Frozen Features ({0}): `{1}` is {2} and is off-limits.".format(
        DISCIPLINE, entry["path"], kind)]
    if entry["why"]:
        parts.append(entry["why"])
    if entry["use"]:
        parts.append("Use the source `{0}` instead.".format(entry["use"]))
    parts.append("If the human explicitly authorized this, escape hatch: "
                 "CSOP_FREEZE=off.")
    return "\n".join(parts)


def main():
    event = csop.load_event()
    if not csop.is_active(DISCIPLINE) or csop.escaped(DISCIPLINE):
        csop.allow()
    tool = event.get("tool_name", "")
    ti = event.get("tool_input", {}) or {}
    entries = _entries()
    if tool in _WRITE_TOOLS:
        for e in entries:                     # hard regex regions first
            if e["regex"] and _regex_hit(e, tool, ti):
                csop.enforce(_FREEZE.get("action"), _region_msg(e))
        for e in entries:                     # prose-only regions nudge
            if e["prose"] and not e["regex"] and _prose_hit(e, ti):
                csop.nudge(_region_msg(e))
    if tool == "Bash":                        # shell restructure of a frozen subtree
        cmd = ti.get("command", "") or ""
        cwd = event.get("cwd", "") or ""      # exempt a worktree by its invocation dir too
        verbs = csop.destructive_verbs(cmd)
        if verbs:
            for e in entries:
                if e["regex"] or e["prose"] or e["mode"] not in ("no-write", "no-restructure"):
                    continue
                if _refs(e["path"], cmd) and not _exempt(e, cmd, cwd):
                    csop.enforce(_FREEZE.get("action"), _restructure_msg(e, verbs))
    texts = _texts(tool, ti)
    if texts:
        for e in entries:                     # whole-path entries
            if e["regex"] or e["prose"]:
                continue
            if _applies(e["mode"], tool) and any(t and e["path"] in t for t in texts):
                csop.enforce(_FREEZE.get("action"), _path_msg(e))
    csop.dropped(_FREEZE.name, DISCIPLINE, _BAD)


if __name__ == "__main__":
    main()
