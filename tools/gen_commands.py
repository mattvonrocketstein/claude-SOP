#!/usr/bin/env python3
"""Render the slash commands in commands/ from the tables that define them.

A nag carries prose (hooks/nags.py); a forward hands a verb to the CLI
(hooks/forwards.py). Every name and alias in either table gets one file, and no
file carries an identity of its own, so an alias cannot drift from its canonical.
A command file invoking the CLI but named by neither table is removed, anything
else is left alone. Usage: gen_commands.py <commands-dir> [--check]
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "hooks"))
import forwards  # noqa: E402
import nags  # noqa: E402

CLI = '"${CLAUDE_PLUGIN_ROOT}/hooks/csop.py"'
MARKER = "hooks/csop.py"
NAG_TEMPLATE = "\n".join((
    "---",
    "description: CSOP -- {description}",
    "allowed-tools: Bash(python3 {cli} *)",
    "disable-model-invocation: true",
    "---",
    "!`python3 {cli} nag {name}`",
    "",
    "Comply with the instruction above.",
    ""))
FORWARD_TEMPLATE = "\n".join((
    "---",
    "description: CSOP -- {description}",
    "argument-hint: \"{hint}\"",
    "allowed-tools: Bash(python3 {cli} *)",
    "disable-model-invocation: true",
    "---",
    "!`python3 {cli} {argv}`",
    "",
    "Show the output above verbatim. No commentary.",
    ""))


def _describe(entry, is_alias):
    if not is_alias:
        return entry.summary
    return "alias for /{0}. {1}".format(
        entry.name, entry.summary[0].upper() + entry.summary[1:])


def render(entry, is_alias):
    """The full text of the command file for a table entry under one of its names."""
    desc = _describe(entry, is_alias)
    if hasattr(entry, "text"):
        return NAG_TEMPLATE.format(description=desc, cli=CLI, name=entry.name)
    argv = ((entry.verb + " ") if entry.verb else "") + "$ARGUMENTS"
    return FORWARD_TEMPLATE.format(description=desc, cli=CLI, hint=entry.hint, argv=argv)


def _table():
    return nags.commands() + forwards.commands()


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def generate(dest, check=False):
    """Write (or, with check, only report) the managed files. Returns the log
    lines and the count of files that are not already correct."""
    wanted = {stem: render(entry, alias) for stem, entry, alias in _table()}
    log, stale = [], 0
    for stem in sorted(wanted):
        path = os.path.join(dest, stem + ".md")
        if _read(path) == wanted[stem]:
            log.append("  {0:<12} {1}.md".format("unchanged", stem))
            continue
        stale += 1
        log.append("  {0:<12} {1}.md".format("stale" if check else "wrote", stem))
        if not check:
            with open(path, "w") as f:
                f.write(wanted[stem])
    for name in sorted(os.listdir(dest)):
        stem, ext = os.path.splitext(name)
        if ext != ".md" or stem in wanted:
            continue
        text = _read(os.path.join(dest, name)) or ""
        if MARKER not in text:
            continue                         # a real command, left untouched
        stale += 1
        log.append("  {0:<12} {1} (retired)".format("stale" if check else "removed", name))
        if not check:
            os.remove(os.path.join(dest, name))
    return log, stale


if __name__ == "__main__":
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    lines, n = generate(argv[0] if argv else "commands", check="--check" in sys.argv)
    print("\n".join(lines))
    if "--check" in sys.argv and n:
        print("{0} file(s) out of date; run `make commands`".format(n), file=sys.stderr)
        sys.exit(1)
