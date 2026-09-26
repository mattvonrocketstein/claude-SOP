#!/usr/bin/env python3
"""PostToolUse bookkeeping: arm the post-turn reminder of any discipline whose
`reminder_on` globs match the file just written.

A reminder is a follow-up on work a turn left behind, so it fires only for a
discipline that acted. Disciplines whose activity is not a path (a test run, a
memory write already matched by its own gate) arm themselves from their own
hook instead. Never blocks.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402

_WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


def main():
    try:
        event = csop.load_event()
        tool = event.get("tool_name", "")
        if tool not in _WRITE_TOOLS:
            sys.exit(0)
        path = csop.write_target(tool, event.get("tool_input", {}) or {})
        if not path:
            sys.exit(0)
        act = csop.effective_active()
        for d in disciplines.DISCIPLINES:
            if d.codename not in act or csop.escaped(d.codename):
                continue
            globs = d.render("reminder_on")
            if globs and csop.path_matches(path, globs):
                csop.touch(d.codename)
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
