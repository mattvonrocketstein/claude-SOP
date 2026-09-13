#!/usr/bin/env python3
"""CSOP nag definitions -- the prose slash commands.

A nag is a fixed instruction a human fires at the model mid-session: no state,
no gate, just text. The text lives here once. `tools/gen_commands.py` renders one
command file per name and per alias, and each of those files embeds the text by
running `csop.py nag <name>`, so an alias is a pointer rather than a copy.
"""


class Nag:
    name = ""
    aliases = ()
    summary = ""                             # the command's frontmatter description
    text = ""                                # what the model is told, verbatim


class Offtopic(Nag):
    name = "offtopic"
    aliases = ("focus",)
    summary = "derailment. Restate the mission and return to focused work."
    text = ("Derailment.  We are trying to focus -- you had a thread to follow but "
            "seem to have lost it.  This is coherent work to do, not tangents, "
            "general cleanup or grooming.  Restate your mission in summary, then "
            "state your specific blockers if any, and return to thread in a focused manner.")


class Unclear(Nag):
    name = "unclear"
    aliases = ("yap",)
    summary = "last turn was fluff. Restate against the mission with relevant facts only."
    text = ("Unclear.  Last turn is too much irrelevant fluff.  Restate in terms of "
            "the mission or session arc, or the critical-path, and with relevant "
            "facts only, plus any *relevant* outcome or results.  Ensure any "
            "proposal you're making is concrete and the next steps are clear.  "
            "Technical jargon is fine, but the cut the bullshit, the opinions, and "
            "vagueries out.  Consider using bullet lists or tables where "
            "appropriate to present data in a compressed form.")


class Unsat(Nag):
    name = "unsat"
    aliases = ()
    summary = "unsatisfied. The turn failed the immediate goal; review and complete it."
    text = ("Unsatisfied.  This turn failed to complete the immediate goals and/or "
            "the session arc at a basic level.  Review recent turns for hints about "
            "what/why.   Avoid evasion, hedging, or non-cooperation and complete the "
            "task.  If you are confused about the problem, check your work directly "
            "like the user would, because indirect probes may be misleading you.  If "
            "you lack clarity regarding the mission, try to resolve it from context.  "
            "If you *still* lack clarity and must avoid thrashing, present discrete "
            "choices for the user to provide needed direction.")


NAGS = [Offtopic, Unclear, Unsat]


def by_name(token):
    """The nag a canonical name or an alias refers to, or None."""
    t = (token or "").strip().lower().lstrip("/")
    for n in NAGS:
        if t == n.name or t in n.aliases:
            return n
    return None


def commands():
    """Every slash command this table owns, as (filename-stem, nag, is_alias)."""
    out = []
    for n in NAGS:
        out.append((n.name, n, False))
        out.extend((a, n, True) for a in n.aliases)
    return sorted(out)
