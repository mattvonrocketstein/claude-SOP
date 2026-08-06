#!/usr/bin/env python3
"""modeline -- the user modeline (end-of-turn CSOP status footer).

A plugin cannot drive the built-in status line, so this Stop hook emits a footer
through the `systemMessage` field, one component per line. Components, format,
and color handling are in docs/gate-internals.md. Never blocks, and stays silent
when every component is empty.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402

GLYPH = "⬥"
BRAND = "CSOP"
TEE, ELBOW = "\u21b3 ", "\u21b3 "


def _c(code, text):
    """Wrap text in an ANSI SGR code; no-op when NO_COLOR is set or text empty."""
    if os.environ.get("NO_COLOR") or not text:
        return text
    return "\033[{0}m{1}\033[0m".format(code, text)


def _segment(label, items):
    """Render one component: `Label: a,b,c`; "" when items is empty."""
    if not items:
        return ""
    return "{0}: {1}".format(_c("36", label), _c("1", ", ".join(items)))


def _hint():
    """A dimmed pointer to the CLI's own help, rather than a usage line the
    footer would have to keep in sync with the CLI."""
    return _c("2", "Use ") + _c("2;3", "/csop help") + _c("2", " for details.")


# ---- components -------------------------------------------------------------
# see the component model in the module docstring before adding one here.

def _disciplines():
    return _segment("Disciplines", sorted(csop.effective_active()))


def _stages():
    """When `pro` is active, every defined stage, the current one bracketed. The
    brackets carry the meaning, not the color, since the app strips styling."""
    if "pro" not in csop.effective_active() or csop.escaped("pro"):
        return ""
    names = list(csop.stages_config().keys())
    if not names:
        return ""
    cur = csop.current_stage()
    items = [_c("1;32", "[" + n + "]") if n == cur else _c("2", n) for n in names]
    body = ", ".join(items) + ("" if cur else _c("2;3", "  (none current)"))
    return "{0}: {1}".format(_c("36", "Stages"), body)


COMPONENTS = [_disciplines, _stages]


def render(extra=()):
    """Assemble the footer: a head line, then every body line hung off it with a
    box-drawing connector, so the block still reads as one unit after the host
    prepends its own preamble. `extra` appends trailing body lines."""
    body = [seg for seg in (component() for component in COMPONENTS) if seg]
    body += [x for x in extra if x]
    if not body:
        return ""
    head = "{0} {1} :: {2}".format(_c("33", GLYPH), _c("1;36", BRAND), _hint())
    hung = [(ELBOW if i == len(body) - 1 else TEE) + line
            for i, line in enumerate(body)]
    return head + "\n" + "\n".join(hung)


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
