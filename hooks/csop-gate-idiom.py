#!/usr/bin/env python3
"""PreToolUse gate: Idiomatic (codename `idiom`) reject rules.

Idiom is mostly awareness, but it also rejects added text matching a project
`reject` rule of {pattern, message}, at the discipline's `action`. Applies to the
edit tools; an empty `reject`, the default, makes this a no-op. Fail-open;
escape hatch CSOP_IDIOM=off.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402

_IDIOM = disciplines.Idiomatic
DISCIPLINE = _IDIOM.codename
_WRITE_TOOLS = ("Edit", "Write", "MultiEdit")


def _added(tool, ti):
    def diff(old, new):
        seen = set((old or "").splitlines())
        return [ln for ln in (new or "").splitlines() if ln not in seen]
    if tool == "Write":
        return diff("", ti.get("content", ""))
    if tool == "Edit":
        return diff(ti.get("old_string", ""), ti.get("new_string", ""))
    out = []
    for e in ti.get("edits", []) or []:
        out += diff(e.get("old_string", ""), e.get("new_string", ""))
    return out


def _rules():
    out = []
    for r in _IDIOM.get("reject") or []:
        try:
            out.append((re.compile(r["pattern"]), r.get("message", "not idiomatic")))
        except Exception:
            pass
    return out


def main():
    event = csop.load_event()
    tool = event.get("tool_name", "")
    if tool not in _WRITE_TOOLS:
        csop.allow()
    active, action = csop.effective(DISCIPLINE, _IDIOM.get("action"))
    if not active or csop.escaped(DISCIPLINE):
        csop.allow()
    rules = _rules()
    if not rules:
        csop.allow()
    ti = event.get("tool_input", {}) or {}
    hits, seen, lines = [], set(), []
    for line in _added(tool, ti):
        for rx, msg in rules:
            if rx.search(line):
                hits.append((msg, line.strip()[:90]))
    if not hits:
        csop.allow()
    for why, snip in hits:
        if (why, snip) in seen:
            continue
        seen.add((why, snip))
        lines.append("  {0}: {1}".format(why, snip))
    csop.enforce(action, "Idiomatic ({0}): {1} non-idiomatic pattern(s) in this "
                 "edit.\n{2}\n\nMatch the surrounding conventions. Escape hatch: "
                 "CSOP_IDIOM=off.".format(DISCIPLINE, len(lines), "\n".join(lines)))


if __name__ == "__main__":
    main()
