#!/usr/bin/env python3
"""PreToolUse gate SKELETON -- one-time SOFT NUDGE (non-blocking).

Archetype (from the core-edit nudge): when an Edit/Write matches a watched
target and the discipline is ACTIVE, emit a one-time reminder, then ALLOW the
edit. Never blocks. Fires at most once per session (tempdir marker).

Consumer TODO: set DISCIPLINE, REMINDER, and the matches() predicate.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402

DISCIPLINE = "example-nudge"                       # TODO consumer
REMINDER = "SOP nudge (skeleton): reminder text."  # TODO consumer


def matches(event):
    """TODO consumer: return True when this edit should trigger the nudge."""
    return False


def main():
    event = csop.load_event()
    if event.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
        csop.allow()
    if not csop.is_active(DISCIPLINE) or csop.escaped(DISCIPLINE):
        csop.allow()
    if not matches(event):
        csop.allow()
    marker = os.path.join(tempfile.gettempdir(),
                          "csop-nudge-{0}".format(DISCIPLINE))
    if os.path.exists(marker):
        csop.allow()                       # already nudged this session
    try:
        open(marker, "w").close()
    except Exception:
        pass
    csop.nudge(REMINDER)


if __name__ == "__main__":
    main()
