#!/usr/bin/env python3
"""Sync CSOP's slash commands into a consumer's .claude/commands directory.

Writes the current command set with plugin-root references rewritten to the
consumer's path, then prunes commands CSOP used to ship and no longer does.
Pruning only ever removes a regular file this tool recognizes as its own
output; anything else in the directory is reported and left alone.
Usage: sync_commands.py <src-dir> <dest-dir> <rel-path-to-plugin> [--dry-run]
"""
import os
import sys

PLACEHOLDER = "${CLAUDE_PLUGIN_ROOT}"
MARKER = "hooks/csop.py"


def render(text, rel):
    """Point a command body at the plugin's location inside the consumer. A rel
    of `.` means the project root itself, the self-hosting case."""
    root = "${CLAUDE_PROJECT_DIR}"
    if rel not in ("", "."):
        root += "/" + rel.strip("/")
    return text.replace(PLACEHOLDER, root)


def is_ours(text):
    """True when a command file matches the shape this tool writes: frontmatter
    that pre-approves the CSOP CLI, plus a body line invoking it. A file failing
    either test is a stranger, so pruning must not touch it."""
    if not text.startswith("---"):
        return False
    head, closed, body = text[3:].partition("\n---")
    if not closed or MARKER not in head:
        return False
    return any(ln.lstrip().startswith("!") and MARKER in ln
               for ln in body.splitlines())


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def _guard(dest):
    """Refuse a destination that is not a commands directory under a claude dir,
    so a mistyped argument cannot aim the prune at an arbitrary tree."""
    parts = os.path.normpath(os.path.abspath(dest)).split(os.sep)
    if parts[-2:] != [".claude", "commands"]:
        raise ValueError(
            "refusing to sync into {0}: expected a path ending in "
            ".claude/commands".format(dest))


def sync(src, dest, rel, dry_run=False):
    """Write the current commands and prune retired ones. Returns the log lines
    and a summary triple of written, pruned, and skipped counts."""
    _guard(dest)
    names = sorted(f for f in os.listdir(src) if f.endswith(".md"))
    if not names:
        raise ValueError("refusing to sync: no commands found in " + src)
    log = []
    if not dry_run:
        os.makedirs(dest, exist_ok=True)
    written = 0
    for name in names:
        body = render(_read(os.path.join(src, name)) or "", rel)
        target = os.path.join(dest, name)
        verb = "would write" if dry_run else "wrote"
        if _read(target) == body:
            verb = "unchanged"
        elif not dry_run:
            with open(target, "w") as f:
                f.write(body)
        written += 1
        log.append("  {0:<12} {1}".format(verb, name))

    pruned = skipped = 0
    if not os.path.isdir(dest):
        return log, (written, pruned, skipped)
    for name in sorted(os.listdir(dest)):
        path = os.path.join(dest, name)
        if name in names or not name.endswith(".md"):
            continue
        if os.path.islink(path) or not os.path.isfile(path):
            skipped += 1
            log.append("  {0:<12} {1} (not a regular file)".format("kept", name))
            continue
        text = _read(path)
        if text is None or not is_ours(text):
            skipped += 1
            log.append("  {0:<12} {1} (not a CSOP command)".format("kept", name))
            continue
        pruned += 1
        log.append("  {0:<12} {1} (retired by CSOP)".format(
            "would prune" if dry_run else "pruned", name))
        if not dry_run:
            os.remove(path)
    return log, (written, pruned, skipped)


if __name__ == "__main__":
    argv = [a for a in sys.argv[1:] if a != "--dry-run"]
    lines, (w, p, s) = sync(argv[0], argv[1], argv[2],
                            dry_run="--dry-run" in sys.argv)
    print("\n".join(lines))
    print("  {0} command(s), {1} pruned, {2} left alone".format(w, p, s))
