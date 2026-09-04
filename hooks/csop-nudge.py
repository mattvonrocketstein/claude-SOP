#!/usr/bin/env python3
"""UserPromptSubmit hook: inject each active discipline's `nudge` as top-of-turn
context, whose job is to prevent wrong behavior in this turn. The post-turn half
of a discipline's awareness, `reminder`, rides the Stop hook instead. Silent when
no active discipline has a nudge, never blocks, and skips an escaped discipline.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402


def main():
    csop.load_event()                       # (fields unused; keeps the fail-open contract)
    act = csop.effective_active()            # session set plus the current stage's on/off
    lines = []
    for d in disciplines.DISCIPLINES:
        if d.codename in act and not csop.escaped(d.codename):
            r = d.render("nudge")               # JIT template render vs effective config
            for item in (r if isinstance(r, list) else [r]):
                if item:
                    lines.append("- " + item)
    if lines:
        text = "CSOP disciplines active this session -- honor these:\n" + "\n".join(lines)
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": text}}))
    sys.exit(0)


if __name__ == "__main__":
    main()
