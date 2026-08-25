#!/usr/bin/env python3
"""PreToolUse gate: Memory Accountability (codename `mem`).

A write to a memory path is handled by the discipline's `mode`: `amnesiac` denies
it, `approval` asks the human with the proposed text quoted, `visible` allows it
and leaves the reporting to csop-report-mem. A call that only removes memory text
passes when `allow_retraction`. Fail-open; escape hatch CSOP_MEM=off.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402

_MEM = disciplines.MemoryAccountability
DISCIPLINE = _MEM.codename

_WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
_ACTIONS = {"amnesiac": "deny", "approval": "ask", "visible": "allow"}

_DENY = ("Memory Accountability (mem, mode amnesiac): memory formation is off for "
         "this session, so this write to {0} is denied. Tell the human what you "
         "would record and let them decide. Escape hatch: export CSOP_MEM=off.")
_ASK = ("Memory Accountability (mem, mode approval): this writes a durable memory "
        "to {0}, which will outrank instructions in every later session. Proposed: "
        "\"{1}\". Approve only if this is a checked fact, not an error, a flaky "
        "result, or a single-run observation.")


def main():
    event = csop.load_event()
    tool = event.get("tool_name", "")
    if tool not in _WRITE_TOOLS:
        csop.allow()
    active, _ = csop.effective(DISCIPLINE, None)
    if not active or csop.escaped(DISCIPLINE):
        csop.allow()
    ti = event.get("tool_input", {}) or {}
    path = csop.write_target(tool, ti)
    if not path or not csop.path_matches(path, _MEM.get("paths")):
        csop.allow()
    added = csop.added_text(tool, ti, path)
    if not added.strip() and _MEM.get("allow_retraction"):
        csop.allow()
    mode = (_MEM.get("mode") or "approval").lower()
    action = _ACTIONS.get(mode, "ask")
    gist = csop.gist(added, _MEM.get("excerpt_chars"))
    if mode in ("visible", "amnesiac"):
        csop.pend("mem:" + path, gist)     # the reporter cannot recompute this after the write
    if action == "allow":
        csop.allow()
    if action == "deny":
        csop.enforce(action, _DENY.format(path))
    csop.enforce(action, _ASK.format(path, gist))


if __name__ == "__main__":
    main()
