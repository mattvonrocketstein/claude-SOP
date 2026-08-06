#!/usr/bin/env python3
"""PreToolUse gate: Entrypoints Sandbox (codename `entrypoints`).

A Bash allow-list, the inverse of a deny gate: a command passes only when every
segment is a basic read or one of the project's blessed `entrypoints`, keeping
the agent on the sanctioned wrapper. Matching is token-prefix and
path-normalized; see docs/gate-internals.md. Fail-open; hatch CSOP_ENTRYPOINTS=off.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402

_ENTRY = disciplines.EntrypointsSandbox
DISCIPLINE = _ENTRY.codename
_SEP = re.compile(r"&&|\|\||;|&|\||\n|\$\(|`|\)")
_ASSIGN = re.compile(r"^\w+=")


def _tokens(segment):
    toks = (segment or "").strip().split()
    while toks and _ASSIGN.match(toks[0]):
        toks = toks[1:]
    if not toks:
        return None
    toks[0] = os.path.basename(toks[0])
    return toks


def _allowed(toks, entries):
    for e in entries:
        et = e.split()
        if len(toks) >= len(et) and toks[:len(et)] == et:
            return True
    return False


def _message(toks, entrypoints):
    blessed = ", ".join(entrypoints) if entrypoints else "(none configured)"
    return ("Entrypoints Sandbox ({0}): `{1}` is not a basic read command nor a "
            "blessed entrypoint, so it is denied. Use a sanctioned entrypoint "
            "instead (blessed: {2}) -- e.g. run the project's wrapper rather than "
            "a raw tool. Escape hatch: export CSOP_ENTRYPOINTS=off.".format(
                DISCIPLINE, " ".join(toks), blessed))


def main():
    event = csop.load_event()
    if event.get("tool_name") != "Bash":
        csop.allow()
    active, action = csop.effective(DISCIPLINE, _ENTRY.get("action"))
    if not active or csop.escaped(DISCIPLINE):
        csop.allow()
    cmd = (event.get("tool_input", {}) or {}).get("command", "") or ""
    entrypoints = _ENTRY.get("entrypoints") or []
    entries = list(_ENTRY.get("reads") or []) + list(entrypoints)
    for seg in _SEP.split(cmd):
        toks = _tokens(seg)
        if toks is None:
            continue
        if not _allowed(toks, entries):
            csop.enforce(action, _message(toks, entrypoints))
    csop.allow()


if __name__ == "__main__":
    main()
