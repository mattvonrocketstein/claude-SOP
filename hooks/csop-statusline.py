#!/usr/bin/env python3
"""statusline -- CSOP status via Claude Code's `statusLine` setting.
Renders the disciplines/stage summary; `csop-modeline.py` is the fallback.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402

GLYPH = "⬥"
BRAND = "CSOP"


def _c(code, text):
    if os.environ.get("NO_COLOR") or not text:
        return text
    return "\033[{0}m{1}\033[0m".format(code, text)


def _segment(label, items):
    if not items:
        return ""
    return "{0}: {1}".format(_c("36", label), _c("1", ",".join(items)))


def _stage_names():
    if "pro" not in csop.effective_active() or csop.escaped("pro"):
        return []
    names = list(csop.stages_config().keys())
    if not names:
        return []
    cur = csop.current_stage()
    out = [_c("1;32", "[" + n + "]") if n == cur else _c("2", n) for n in names]
    return out if cur else out + [_c("2;3", "(none current)")]


def render():
    segs = [s for s in (_segment("Disciplines", sorted(csop.effective_active())),
                        _segment("Stages", _stage_names())) if s]
    if not segs:
        return ""
    return "{0} {1} :: {2}".format(_c("33", GLYPH), _c("1;36", BRAND), "  ".join(segs))


def main():
    try:
        json.loads(sys.stdin.read() or "{}")
    except Exception:
        pass
    try:
        line = render()
    except Exception:
        line = ""
    if line:
        print(line)


if __name__ == "__main__":
    main()
