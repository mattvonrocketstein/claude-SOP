#!/usr/bin/env python3
"""CSOP forwarding slash commands: the ones that hand a verb to the CLI.

A forward is a command whose body runs `csop.py <verb>` with the typed arguments
and shows the output. Its identity lives here once, so an alias such as /disc is
a second name for a table entry rather than a copy of a file.
`tools/gen_commands.py` renders one command file per name and per alias.
"""


class Forward:
    name = ""
    aliases = ()
    verb = ""                                # the CLI verb, empty passes args straight through
    hint = ""                                # the frontmatter argument-hint
    summary = ""                             # the frontmatter description


class Sop(Forward):
    name = "sop"
    aliases = ("disc", "discipline")
    verb = ""
    hint = "enable <name|codename> | list | catalog | show <name>"
    summary = "enable / list / catalog / show disciplines (SOPs); no-arg = list."


class SopDisable(Forward):
    name = "sop-disable"
    verb = "disable"
    hint = "<name|codename|all>"
    summary = "deactivate a discipline (or `all`). Human-only, the inverse of `/sop enable`."


class Stage(Forward):
    name = "stage"
    verb = "stage"
    hint = "[<stage-name>]"
    summary = "show the current stage and available stages, or set the current stage."


class Ticket(Forward):
    name = "ticket"
    verb = "ticket"
    hint = "[<issue-id>]"
    summary = "show the declared ticket, or declare one over the current stage."


class Promote(Forward):
    name = "promote"
    verb = "promote"
    hint = "[<target-stage>]"
    summary = "climb the stage ladder: promote the current stage to its next stage."


class Demote(Forward):
    name = "demote"
    verb = "demote"
    hint = "[<target-stage>]"
    summary = "step down the stage ladder: demote the current stage to a `from` source."


FORWARDS = [Sop, SopDisable, Stage, Ticket, Promote, Demote]


def by_name(token):
    """The forward a canonical name or an alias refers to, or None."""
    t = (token or "").strip().lower().lstrip("/")
    for f in FORWARDS:
        if t == f.name or t in f.aliases:
            return f
    return None


def commands():
    """Every slash command this table owns, as (filename-stem, forward, is_alias)."""
    out = []
    for f in FORWARDS:
        out.append((f.name, f, False))
        out.extend((a, f, True) for a in f.aliases)
    return sorted(out)
