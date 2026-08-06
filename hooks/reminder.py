#!/usr/bin/env python3
"""UserPromptSubmit hook: inject each ACTIVE discipline's `reminder` at the TOP
of the turn (additionalContext), so the protocol stays in the model's context
while the discipline is active. This is the AWARENESS half of a discipline.

Silent when nothing is active or no active discipline has a reminder. Never
blocks (exit 0). An escaped discipline (CSOP_<NAME>=off) is skipped.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402


def main():
    csop.load_event()                       # (fields unused; keeps the fail-open contract)
    act = csop.active()
    lines = []
    for d in disciplines.DISCIPLINES:
        if d.codename in act and not csop.escaped(d.codename):
            r = d.render("reminder")            # JIT template render vs effective config
            if r:
                lines.append("- " + r)
    if lines:
        text = "CSOP disciplines active this session -- honor these:\n" + "\n".join(lines)
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": text}}))
    sys.exit(0)


if __name__ == "__main__":
    main()
