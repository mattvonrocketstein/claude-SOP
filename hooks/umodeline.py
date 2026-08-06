#!/usr/bin/env python3
"""umodeline -- the USER MODELINE (end-of-turn CSOP status footer).

A plugin cannot drive the built-in status line, so this `Stop` hook emits a
one-line status footer via the `systemMessage` JSON field (the user-visible
Stop-hook channel; raw stdout is NOT shown). Format:

    <glyph> CSOP :: ( Disciplines: d1,d2 ) [ ( NextComponent: .. ) ... ]

COMPONENT MODEL: the modeline is a list of COMPONENTS. Each component is a
zero-arg callable returning a rendered segment `( Label: a,b,c )`, or "" when it
has nothing to show. `_disciplines` is the FIRST component and the template for
any future one: read some state, return `_segment(Label, items)`; register it by
appending to COMPONENTS.

SAFETY: never blocks (exit 0, guards on stop_hook_active); silent when every
component is empty. Color is best-effort ANSI (systemMessage may restyle it) and
is disabled when NO_COLOR is set.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402

GLYPH = "⬥"
BRAND = "CSOP"


def _c(code, text):
    """Wrap text in an ANSI SGR code; no-op when NO_COLOR is set or text empty."""
    if os.environ.get("NO_COLOR") or not text:
        return text
    return "\033[{0}m{1}\033[0m".format(code, text)


def _segment(label, items):
    """Render one component: `( Label: a,b,c )`; "" when items is empty."""
    if not items:
        return ""
    return "( {0}: {1} )".format(_c("36", label), _c("1", ",".join(items)))


# ---- components -------------------------------------------------------------
# Each COMPONENT is a zero-arg callable -> a segment string (or "" to omit).
# `_disciplines` is the MODEL for the rest: read some state, return
# `_segment(Label, items)`. Add a new component function below, then register it
# in COMPONENTS (order = left-to-right on the modeline).

def _disciplines():
    return _segment("Disciplines", sorted(csop.active()))


COMPONENTS = [_disciplines]


def render():
    """Assemble the modeline from non-empty components; "" if all are empty."""
    segments = [seg for seg in (component() for component in COMPONENTS) if seg]
    if not segments:
        return ""
    head = "{0} {1} ::".format(_c("33", GLYPH), _c("1;36", BRAND))
    return head + " " + " ".join(segments)


def main():
    event = csop.load_event()
    if event.get("stop_hook_active"):
        sys.exit(0)                     # re-entrancy guard: never join a block loop
    line = render()
    if line:
        print(json.dumps({"systemMessage": line}))
    sys.exit(0)                          # ALWAYS allow the turn to end


if __name__ == "__main__":
    main()
