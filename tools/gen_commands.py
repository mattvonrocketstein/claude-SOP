#!/usr/bin/env python3
"""Render the prose slash commands in commands/ from the nags table.

Every nag name and alias gets one file, and each embeds the canonical text at run
time rather than copying it. Only these files are managed: one that invokes
`csop.py nag` but answers to no name in the table is removed, anything else is
left alone. Usage: gen_commands.py <commands-dir> [--check]
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "hooks"))
import nags  # noqa: E402

CLI = '"${CLAUDE_PLUGIN_ROOT}/hooks/csop.py"'
MARKER = "csop.py\" nag "
COMMAND_TEMPLATE = "\n".join((
    "---",
    "description: CSOP -- {description}",
    "allowed-tools: Bash(python3 {cli} *)",
    "disable-model-invocation: true",
    "---",
    "!`python3 {cli} nag {name}`",
    "",
    "Comply with the instruction above.",
    ""))


def render(nag, is_alias):
    desc = ("alias for /{0}. {1}".format(nag.name, nag.summary[0].upper() + nag.summary[1:])
            if is_alias else nag.summary)
    return COMMAND_TEMPLATE.format(description=desc, cli=CLI, name=nag.name)


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def generate(dest, check=False):
    """Write (or, with check, only report) the managed files. Returns the log
    lines and the count of files that are not already correct."""
    wanted = {stem: render(nag, alias) for stem, nag, alias in nags.commands()}
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
