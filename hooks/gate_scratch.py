#!/usr/bin/env python3
"""PreToolUse gate: Scratch (destructive-operation guard).

When `scratch` is active, a Bash command matching any of the discipline's
`deny_patterns` (dangerous recursive+force file removal, the nuclear git
options, shred / mkfs / dd) is DENIED. The safe alternative is to MOVE content
out of circulation into the discipline's `scratch_dir` rather than deleting it.

Fail-open; escape hatch CSOP_SCRATCH=off. Bad regexes in config are skipped.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402

_SCRATCH = disciplines.Scratch
DISCIPLINE = _SCRATCH.codename


def _compiled():
    out = []
    for p in _SCRATCH.get("deny_patterns"):
        try:
            out.append(re.compile(p))
        except Exception:
            pass
    return out


_PATTERNS = _compiled()


def main():
    event = csop.load_event()
    if event.get("tool_name") != "Bash":
        csop.allow()
    if not csop.is_active(DISCIPLINE) or csop.escaped(DISCIPLINE):
        csop.allow()
    cmd = (event.get("tool_input", {}) or {}).get("command", "") or ""
    if any(p.search(cmd) for p in _PATTERNS):
        csop.deny("Scratch (destructive-op guard): this command is irreversibly "
                  "destructive and is DENIED. Take the content out of circulation "
                  "by moving it into `{0}` instead, or the human runs it. "
                  "(CSOP_SCRATCH=off.)".format(_SCRATCH.get("scratch_dir")))
    csop.allow()


if __name__ == "__main__":
    main()
