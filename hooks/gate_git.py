#!/usr/bin/env python3
"""PreToolUse gate: Human Accountability (codename `hacc`).

When `hacc` is active, git is READ-ONLY for the agent: a git command that MUTATES
history / branches / working tree / remote is DENIED via a `deny` permission
decision -- the agent cannot commit / stash / checkout / push / rm / etc. A human
must run those directly (or set CSOP_HACC=off). Read-only git and `git add`
(staging) pass through.

HACC protects CORE, not iso trees. When `iso` is active, git history ops CONFINED
to an iso tree are exempt: rebasing a tree onto core for freshness (and the
commits that needs) can never produce a quiet commit into core. A command counts
as iso-scoped only when it runs inside the tree via `git -C <isodir> ...` or `cd
<isodir> && ...`; ops that escape the tree (push / pull, or repo-wide surgery
like gc / prune / filter-*) stay denied, and merging an iso branch from core is
NOT iso-scoped. Promotion into core is by EDITS/INSERTS, never a git merge.

Fail-open; escape hatch CSOP_HACC=off. `add` is deliberately NOT gated.
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
# The git subcommands to DENY come from the discipline's `deny_list` property
# (project-overridable via .claude/csop.json). NOT gated (stay allowed): add,
# status, log, diff, show, blame, fetch, ls-*, rev-parse, config --get, ...
_DENY = _HACC.get("deny_list")
_MUTATE = re.compile(r"\b(" + "|".join(re.escape(x) for x in _DENY) + r")\b")

_ISODIR = disciplines.IsoTree.get("dir")
_ISO = disciplines.IsoTree.codename
_ISO_SCOPED = re.compile(r"git\s+-C\s+\S*" + re.escape(_ISODIR)
                         + r"|cd\s+\S*" + re.escape(_ISODIR) + r"\S*\s*(?:&&|;)")
_NEVER = re.compile(r"\b(push|pull|gc|prune|filter-branch|filter-repo)\b")


def _iso_exempt(cmd):
    """A denied git write is exempt when iso is active and the command runs
    INSIDE an iso tree (a disposable sandbox), unless it escapes the tree."""
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
    csop.deny("Human Accountability (hacc): git write to CORE is DENIED -- a "
              "human runs core git (or CSOP_HACC=off); reads and `git add` are "
              "fine. To PROMOTE an iso tree, rebase it for freshness INSIDE the "
              "tree (`git -C {0}<name> rebase <core>`), then reconcile into core "
              "by EDITS/INSERTS -- never a git merge/commit into core.".format(_ISODIR))


if __name__ == "__main__":
    main()
