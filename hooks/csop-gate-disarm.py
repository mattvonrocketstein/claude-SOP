#!/usr/bin/env python3
"""PreToolUse gate: only a human disarms a discipline.

Every route from a tool call to a smaller active set is shut: the `disable` and
`reset` verbs, an `enable` that drops something by conflict, a write to the state
dir, and a command relocating that dir by env var. The canonical invocation a
slash command produces is escalated to a permission prompt only the human can
answer. Always on, fails closed, no hatch. See docs/gate-internals.md.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402

_CLI = r"csop(?:\.py)?[\"']?"
_VERB = re.compile(_CLI + r"\s+(?:\S+\s+)*?(disable|reset)\b")
_ENABLE = re.compile(_CLI + r"\s+enable\s+([A-Za-z][\w-]*)")
_RELOCATE = re.compile(r"\bCLAUDE_(?:PLUGIN_DATA|PROJECT_DIR)\s*=")
_STATE = re.compile(r"csop-state\b|\bactive\.json\b")
_CANONICAL = re.compile(r"^\s*(?:python[0-9.]*\s+)?[\"']?\S*csop\.py[\"']?"
                        r"\s+disable\s+[A-Za-z][\w-]*\s*$")
_WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")

_ASK = ("CSOP: `{0}` disarms a discipline. Approve only if you just ran a "
        "/sop-disable or /sop disable slash command yourself. If the agent "
        "asked for this, deny it: disciplines are not the agent's to switch off.")
_BLOCK = ("CSOP disarm rail: {0}. Disabling a discipline is the human's call, not "
          "yours. Ask them to run `/sop-disable <name>`; do not retry, and do not "
          "route around this by editing state, relocating it, or enabling a "
          "conflicting discipline. This rail is always on and has no escape hatch.")


def _under_state(path):
    try:
        root = os.path.realpath(os.path.dirname(csop.state_path("x")))
        return os.path.commonpath([os.path.realpath(path), root]) == root
    except Exception:
        return False


def _bash_reason(cmd):
    """Why this shell command counts as a disarm, or None if it does not."""
    if _VERB.search(cmd):
        return "this runs a disarming csop verb"
    if _RELOCATE.search(cmd) and ("csop" in cmd or _STATE.search(cmd)):
        return "this relocates the csop state dir, which reads as nothing active"
    if _STATE.search(cmd) and csop.mutates_files(cmd):
        return "this writes the csop state file directly"
    m = _ENABLE.search(cmd)
    if m:
        direct, cascade = csop.enable_drops(m.group(1))
        if direct or cascade:
            return "enabling {0} would switch off {1} by conflict".format(
                m.group(1), " ".join(sorted(direct | cascade)))
    return None


def main():
    event = csop.load_event()
    tool = event.get("tool_name")
    ti = event.get("tool_input", {}) or {}
    if tool == "Bash":
        cmd = ti.get("command", "") or ""
        reason = _bash_reason(cmd)
        if not reason:
            csop.allow()
        if _CANONICAL.match(cmd):
            csop.ask(_ASK.format(cmd.strip()))
        csop.block(_BLOCK.format(reason))
    if tool in _WRITE_TOOLS:
        fp = ti.get("file_path", "") or ti.get("notebook_path", "") or ""
        if fp and _under_state(fp):
            csop.block(_BLOCK.format("`{0}` is csop's own state".format(fp)))
    csop.allow()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        csop.block(_BLOCK.format("the disarm rail errored ({0}), so it fails "
                                 "closed".format(exc)))
