#!/usr/bin/env python3
"""UserPromptSubmit hook: answer a read-only CSOP slash command directly.

The CLI's output is fixed text, so routing it through the model costs a turn and
risks a paraphrase. This hook runs the read-only verbs itself and blocks the
prompt with the output as the message, so nothing is queried. The mutating verbs
keep the old path: their permission prompt is what holds disarming in human
hands. Fail-open, and silent on any prompt it does not recognize.
"""
import io
import json
import os
import re
import sys
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402

VERBS = ("list", "catalog", "show", "help")
NAMES = ("sop", "disc", "discipline")
_TAGGED = re.compile(r"<command-name>\s*/?([\w-]+)\s*</command-name>"
                     r"(?:\s*<command-args>(.*?)</command-args>)?", re.S)
_TYPED = re.compile(r"\A\s*/([\w-]+)(?:\s+(.*))?\Z", re.S)


def _argv(prompt):
    """The CLI argv this prompt asks for, or None when it is not ours to answer.
    Both prompt shapes are accepted, since the harness expands a slash command
    into tags but a typed line may still arrive raw."""
    m = _TAGGED.search(prompt) or _TYPED.match(prompt)
    if not m or (m.group(1) or "").lower() not in NAMES:
        return None
    argv = (m.group(2) or "").split() or ["list"]
    return argv if argv[0] in VERBS else None


def main():
    try:
        argv = _argv(csop.load_event().get("prompt") or "")
        if argv:
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                csop._cli(argv)
            text = (out.getvalue() + err.getvalue()).rstrip()
            if text:
                print(json.dumps({"decision": "block", "reason": text,
                                  "suppressOriginalPrompt": True}))
    except Exception:
        pass                             # fail open: the command runs the old way
    sys.exit(0)


if __name__ == "__main__":
    main()
