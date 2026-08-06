#!/usr/bin/env python3
"""PreToolUse gate: Robot Accountability (codename `racc`).

A Bash command that writes a file in place is denied, so the change goes through
the Edit or Write tool where the human sees a diff. Caught: in-place editors,
redirects and heredocs, patches, and an inline interpreter script that opens a
file for writing. Read-only shell passes. Fail-open; escape hatch CSOP_RACC=off.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402

_RACC = disciplines.RobotAccountability
DISCIPLINE = _RACC.codename


def main():
    event = csop.load_event()
    if event.get("tool_name") != "Bash":
        csop.allow()
    active, action = csop.effective(DISCIPLINE, _RACC.get("action"))
    if not active or csop.escaped(DISCIPLINE):
        csop.allow()
    cmd = (event.get("tool_input", {}) or {}).get("command", "") or ""
    found = csop.write_constructs(cmd)
    if not found:
        csop.allow()
    csop.enforce(action,
                 "Robot Accountability (racc): this shell command writes a file in "
                 "place ({0}), which hides the change. Make the edit through the "
                 "Edit or Write tool so the diff is visible. Escape hatch: export "
                 "CSOP_RACC=off.".format(", ".join(found)))


if __name__ == "__main__":
    main()
