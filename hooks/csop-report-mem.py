#!/usr/bin/env python3
"""PostToolUse reporter: Memory Accountability (codename `mem`).

A memory write that landed is queued as a notice, so the end-of-turn modeline
names it. That is the whole mechanism under `visible`, and an alarm under
`amnesiac`, where reaching this hook means the permission layer dropped the
denial. Silent under `approval`. Never blocks; escape hatch CSOP_MEM=off.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402

_MEM = disciplines.MemoryAccountability
DISCIPLINE = _MEM.codename

_WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")

_VISIBLE = "memory written to {0}: \"{1}\""
_ALARM = ("memory written to {0} despite mode amnesiac, so the permission layer "
          "dropped the denial (it does that under bypassPermissions). Retract it "
          "if it should not have formed. Recorded: \"{1}\"")


def main():
    try:
        event = csop.load_event()
        tool = event.get("tool_name", "")
        active, _ = csop.effective(DISCIPLINE, None)
        if tool not in _WRITE_TOOLS or not active or csop.escaped(DISCIPLINE):
            sys.exit(0)
        mode = (_MEM.get("mode") or "approval").lower()
        if mode not in ("visible", "amnesiac"):
            sys.exit(0)
        ti = event.get("tool_input", {}) or {}
        path = csop.write_target(tool, ti)
        if not path or not csop.path_matches(path, _MEM.get("paths")):
            sys.exit(0)
        gist = csop.take("mem:" + path)
        if gist is None:
            added = csop.added_text(tool, ti, path, subtract_prior=False)
            gist = csop.gist(added, _MEM.get("excerpt_chars"))
        if not gist:
            sys.exit(0)
        csop.push_notice((_ALARM if mode == "amnesiac" else _VISIBLE).format(path, gist))
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
