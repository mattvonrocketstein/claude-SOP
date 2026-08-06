#!/usr/bin/env python3
"""PreToolUse gate: Dreamer write-confinement (codename `dream`).

Dreamer is ideation mode: diverge, capture ideas, don't build. When `dream` is
active, a structured write (Edit / Write / MultiEdit / NotebookEdit) whose target
is outside the scratch area is stopped -- ideas belong in scratch, not in core
code. Reads are never gated. Enforcement strength is the discipline's action.
Fail-open; escape hatch CSOP_DREAM=off.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402

_DREAM = disciplines.Dreamer
DISCIPLINE = _DREAM.codename
_WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


def main():
    event = csop.load_event()
    if event.get("tool_name") not in _WRITE_TOOLS:
        csop.allow()
    active, action = csop.effective(DISCIPLINE, _DREAM.get("action"))
    if not active or csop.escaped(DISCIPLINE):
        csop.allow()
    ti = event.get("tool_input", {}) or {}
    path = ti.get("file_path", "") or ti.get("notebook_path", "") or ""
    area = _DREAM.get("home")
    if not path or area in path:
        csop.allow()
    csop.enforce(action,
                 "Dreamer ({0}): ideation mode -- writes are confined to `{1}`. "
                 "This write to `{2}` is outside it. Capture the idea as a note in "
                 "`{1}`, don't build it in core yet. Escape hatch: "
                 "CSOP_DREAM=off.".format(DISCIPLINE, area, path))


if __name__ == "__main__":
    main()
