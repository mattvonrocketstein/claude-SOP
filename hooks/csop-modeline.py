#!/usr/bin/env python3
"""modeline -- the user modeline (end-of-turn CSOP status footer).

A plugin cannot drive the built-in status line, so this Stop hook emits a footer
through the `systemMessage` field, one component per line. Components, format,
and color handling are in docs/gate-internals.md. Never blocks, and stays silent
when every component is empty.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402

GLYPH = "⬥"
BRAND = "CSOP"
INNER = 54                    # content columns before the host wraps for us
TOP, RAIL, FOOT = "\u250f", "\u2503", "\u2517"   # one box family: mixing families mixes metrics
_ANSI = re.compile("\033\\[[0-9;]*m")


def _c(code, text):
    """Wrap text in an ANSI SGR code; no-op when NO_COLOR is set or text empty."""
    if os.environ.get("NO_COLOR") or not text:
        return text
    return "\033[{0}m{1}\033[0m".format(code, text)


def _vis(text):
    """Printed width: the string minus its styling, since padding must line the
    rails up on what the reader sees, not on what the escape codes cost."""
    return len(_ANSI.sub("", text))


def _fill(tokens, width):
    """Greedy fill into rows no wider than `width`, never splitting a token."""
    rows, cur = [], ""
    for tok in tokens:
        cand = (cur + " " + tok) if cur else tok
        if cur and _vis(cand) > width:
            rows.append(cur)
            cur = tok
        else:
            cur = cand
    return rows + [cur] if cur else rows


def _balance(tokens, width):
    """Fill into the same number of rows `_fill` needs, but at the narrowest
    width that still reaches that count, so the rows come out near-even instead
    of one long row and a short remainder."""
    rows = _fill(tokens, width)
    if len(rows) < 2:
        return rows
    lo, hi = max(_vis(t) for t in tokens), width
    while lo < hi:
        mid = (lo + hi) // 2
        if len(_fill(tokens, mid)) <= len(rows):
            hi = mid
        else:
            lo = mid + 1
    return _fill(tokens, lo)


def _segment(label, items):
    """Render one component as box rows: `Label: a, b, c` on one row when it
    fits, else the label alone and the list wrapped and indented beneath it."""
    if not items:
        return []
    toks = [it + ("," if i < len(items) - 1 else "")
            for i, it in enumerate(items)]
    head = "{0}: {1}".format(_c("36", label), " ".join(toks))
    if _vis(head) <= INNER:
        return [head]
    return [_c("36", label) + ":"] + ["  " + r for r in _balance(toks, INNER - 2)]


def _hint():
    """A dimmed pointer to the CLI's own help, rather than a usage line the
    footer would have to keep in sync with the CLI."""
    return _c("2", "Use ") + _c("2;3", "/sop help") + _c("2", " for details.")


# ---- components -------------------------------------------------------------
# see the component model in the module docstring before adding one here.

def _disciplines():
    return _segment("Active Disciplines",
                    [_c("1", d) for d in sorted(csop.effective_active())])


def _stages():
    """When `pro` is active, the stage the work is in. Only the current one: the
    roster is what `/sop stage` prints, and the footer answers where you are."""
    if "pro" not in csop.effective_active() or csop.escaped("pro"):
        return []
    if not csop.stages_config():
        return []
    cur = csop.current_stage()
    return ["{0} :: {1}".format(_c("36", "Active Stage"),
                                _c("1;32", cur) if cur
                                else _c("2;3", "(none current)"))]


COMPONENTS = [_disciplines]
TAIL = [_stages]


def render(extra=()):
    """Assemble the footer: a one-glyph gutter column, corner to rail to corner.
    Every glyph comes from the heavy box family, which fonts ship complete or
    not at all, so the column cannot bend the way a mixed set does. There is no
    horizontal border, since no character that could draw one holds its width.
    Wrapping happens here rather than in the host, which wraps at a fixed column
    mid-word. `extra` appends rows."""
    body = []
    for component in COMPONENTS:
        body += component()
    for x in extra:
        if x:
            body += _balance(x.split(), INNER)
    for component in TAIL:
        body += component()
    if not body:
        return ""
    lines = ["{0} :: {1}".format(_c("1;36", BRAND), _hint())] + body
    return "\n".join(
        "{0} {1}".format(TOP if i == 0 else FOOT if i == len(lines) - 1
                         else RAIL, line)
        for i, line in enumerate(lines))


def _reminders():
    """Each active discipline's post-turn `reminder` (follow-up tasks), rendered."""
    out, act = [], csop.effective_active()
    for d in disciplines.DISCIPLINES:
        if d.codename in act and not csop.escaped(d.codename):
            r = d.render("reminder")
            if r:
                out.append("{0}: {1}".format(_c("36", d.name), r))
    return out


def main():
    event = csop.load_event()
    if event.get("stop_hook_active"):
        sys.exit(0)                     # re-entrancy guard: never join a block loop
    extra = list(_reminders())
    extra += ["{0} CSOP: {1}".format(_c("33", "⚠"), n) for n in csop.drain_notices()]
    line = render(extra)
    if line:
        print(json.dumps({"systemMessage": line}))
    sys.exit(0)                          # always allow the turn to end


if __name__ == "__main__":
    main()
