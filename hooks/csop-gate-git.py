#!/usr/bin/env python3
"""PreToolUse gate: Human Accountability (codename `hacc`).

The agent may only read from version control. Each git call in a command is
classified by its own subcommand: one on the discipline's read_list passes,
anything else is denied so a human runs it. When `iso` is active, a call
directed into an iso tree with `git -C` is exempt; see scratch/gate-internals.md.
Fail-open; escape hatch CSOP_HACC=off.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402

_HACC = disciplines.HumanAccountability
DISCIPLINE = _HACC.codename                              # "hacc"

_GIT = re.compile(r"\bgit\b")
# read subcommands come from the discipline's project-overridable read_list.
_READ = set(_HACC.get("read_list"))

_ISODIR = disciplines.IsoTree.get("home")
_ISO = disciplines.IsoTree.codename
# git's own global options, which sit before the subcommand.
_VALUED = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path")
_NEVER = ("push", "pull", "gc", "prune", "filter-branch", "filter-repo")


def _invocations(cmd):
    """Each git call in the command, as (subcommand, iso_scoped). A subcommand
    of None means the call could not be classified."""
    for m in _GIT.finditer(cmd):
        yield _classify(cmd[m.end():])


def _classify(tail):
    """Read one git call's subcommand, skipping the global options that precede
    it, and note whether the call was directed into an iso tree. A subcommand
    that only reads under certain subverbs is returned as both words."""
    iso_scoped = False
    tokens = re.split(r"[\s;|&()]+", tail.strip())
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if not tok:
            i += 1
        elif tok in _VALUED:
            val = tokens[i + 1] if i + 1 < len(tokens) else ""
            iso_scoped = iso_scoped or (tok == "-C" and _ISODIR in val)
            i += 2
        elif tok.startswith("--") and "=" in tok:
            iso_scoped = iso_scoped or _ISODIR in tok
            i += 1
        elif tok.startswith("-"):
            i += 1
        else:
            return _subcommand(tok, tokens[i + 1:]), iso_scoped
    return None, iso_scoped


def _subcommand(tok, rest):
    """The subcommand to match, widened to two words when the read_list draws
    its line at the subverb rather than the subcommand."""
    if not any(x.startswith(tok + " ") for x in _READ):
        return tok
    subverb = next((t for t in rest if t and not t.startswith("-")), "")
    return (tok + " " + subverb).strip()


def _iso_exempt(sub, iso_scoped):
    """A git write is exempt when iso is active and this call was directed into
    an iso tree (a disposable sandbox), unless it reaches beyond the tree."""
    return (csop.is_active(_ISO) and iso_scoped and sub not in _NEVER)


def main():
    event = csop.load_event()
    if event.get("tool_name") != "Bash":
        csop.allow()
    if not csop.is_active(DISCIPLINE) or csop.escaped(DISCIPLINE):
        csop.allow()                     # discipline off -> no gating
    cmd = (event.get("tool_input", {}) or {}).get("command", "") or ""
    for sub, iso_scoped in _invocations(cmd):
        if sub in _READ or _iso_exempt(sub, iso_scoped):
            continue                     # a read, or an iso-sandbox history op
        csop.deny(
            "Human Accountability (hacc): `git {0}` is not a read, so a human "
            "runs it (or CSOP_HACC=off); reads and `git add` are fine. To "
            "promote an iso tree, rebase it for freshness inside the tree "
            "(`git -C {1}<name> rebase <core>`), then reconcile into core by "
            "edits/inserts -- never a git merge/commit into core.".format(
                sub or "<unparsed>", _ISODIR))
    csop.allow()


if __name__ == "__main__":
    main()
