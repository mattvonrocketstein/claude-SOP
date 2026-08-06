#!/usr/bin/env python3
"""PreToolUse gate: Human Accountability (codename `hacc`).

The agent may only read from version control: a command mutating history,
branches, working tree, or remote is denied, so a human runs it. Reads and
staging pass. When `iso` is active, history ops confined to an iso tree are
exempt; see docs/gate-internals.md. Fail-open; escape hatch CSOP_HACC=off.
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
# denied subcommands come from the discipline's project-overridable deny_list.
_DENY = _HACC.get("deny_list")
_MUTATE = re.compile(r"\b(" + "|".join(re.escape(x) for x in _DENY) + r")\b")

_ISODIR = disciplines.IsoTree.get("home")
_ISO = disciplines.IsoTree.codename
_ISO_SCOPED = re.compile(r"git\s+-C\s+\S*" + re.escape(_ISODIR)
                         + r"|cd\s+\S*" + re.escape(_ISODIR) + r"\S*\s*(?:&&|;)")
_NEVER = re.compile(r"\b(push|pull|gc|prune|filter-branch|filter-repo)\b")


def _iso_exempt(cmd):
    """A denied git write is exempt when iso is active and the command runs
    inside an iso tree (a disposable sandbox), unless it escapes the tree."""
    return (csop.is_active(_ISO) and bool(_ISO_SCOPED.search(cmd))
            and not _NEVER.search(cmd))


def main():
    event = csop.load_event()
    if event.get("tool_name") != "Bash":
        csop.allow()
    if not csop.is_active(DISCIPLINE) or csop.escaped(DISCIPLINE):
        csop.allow()                     # discipline off -> no gating
    cmd = (event.get("tool_input", {}) or {}).get("command", "") or ""
    if not _GIT.search(cmd) or not _MUTATE.search(cmd):
        csop.allow()                     # not a git write -> no sign-off needed
    if _iso_exempt(cmd):
        csop.allow()                     # iso sandbox: local history op, no core impact
    csop.deny("Human Accountability (hacc): git write to core is denied -- a "
              "human runs core git (or CSOP_HACC=off); reads and `git add` are "
              "fine. To promote an iso tree, rebase it for freshness inside the "
              "tree (`git -C {0}<name> rebase <core>`), then reconcile into core "
              "by edits/inserts -- never a git merge/commit into core.".format(_ISODIR))


if __name__ == "__main__":
    main()
