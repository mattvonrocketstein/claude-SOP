#!/usr/bin/env python3
"""PostToolUse reporter: Testing Discipline (codename `tdd` and subclasses).

A test run that landed is queued as a notice naming its scope and the counts
from its output, so the end-of-turn modeline shows what ran. A tool edit to a
`src_globs` path is remembered so the gate can suggest that file's tests.
Never blocks; escape hatch CSOP_TDD=off.
"""
import importlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402

gate = importlib.import_module("csop-gate-tdd")

_WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
_COUNTS = re.compile(r"(?<!\d)\d+ (?:passed|failed|errors?|skipped|xfailed|xpassed|"
                     r"deselected|warnings?)\b|\bRan \d+ tests?\b|\bOK\b|\bFAILED\b")


def _counts(resp):
    if isinstance(resp, dict):
        text = "\n".join(str(v) for v in resp.values())
    else:
        text = resp if isinstance(resp, str) else json.dumps(resp)
    found = []
    for m in _COUNTS.findall(text):
        if m not in found:
            found.append(m)
    return ", ".join(found[:6])


def main():
    try:
        event = csop.load_event()
        tool = event.get("tool_name", "")
        members = gate.family()
        if not members:
            sys.exit(0)
        ti = event.get("tool_input", {}) or {}
        if tool in _WRITE_TOOLS:
            path = csop.write_target(tool, ti)
            if path and csop.path_matches(path, gate.listed(members, "src_globs")):
                p = csop.state_path(gate.LAST_SRC)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w") as f:
                    json.dump({"path": path}, f)
            sys.exit(0)
        if tool != "Bash":
            sys.exit(0)
        cmd = ti.get("command", "") or ""
        scope = csop.take("tdd:" + cmd)
        if scope is None:
            sys.exit(0)
        counts = _counts(event.get("tool_response", ""))
        tail = " [{0}]".format(counts) if counts else ""
        csop.push_notice("tests ran ({0}): {1}{2}".format(
            scope, csop.oneline(cmd, 100), tail))
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
