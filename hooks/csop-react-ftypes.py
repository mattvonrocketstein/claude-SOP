#!/usr/bin/env python3
"""PostToolUse gate: Filetypes (codename `ftypes`).

After an edit, for each project `types` entry whose globs match the file, inject
that entry's `reminder` and, if it has a `command`, run it and feed the captured
output back to the model. That capture is the only way the model sees a command's
output. Empty by default. Fail-open; escape hatch CSOP_FTYPES=off.
"""
import fnmatch
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402

_D = disciplines.Filetypes
DISCIPLINE = _D.codename
_WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
_LIMIT = 4000


def _match(path, globs):
    p = (path or "").replace("\\", "/")
    for g in globs or []:
        if fnmatch.fnmatch(p, g) or fnmatch.fnmatch(p, "*/" + g):
            return True
    return False


def _run(cmd, cwd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=30, cwd=cwd)
    except Exception as e:
        return "command errored: {0}".format(e)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if len(out) > _LIMIT:
        out = out[:_LIMIT] + " ...(truncated)"
    tail = "" if r.returncode == 0 else " (exit {0})".format(r.returncode)
    if not out and not tail:
        return ""
    return "$ {0}{1}\n{2}".format(cmd, tail, out).rstrip()


def main():
    event = csop.load_event()
    if event.get("tool_name") not in _WRITE_TOOLS:
        csop.allow()
    if not csop.is_active(DISCIPLINE) or csop.escaped(DISCIPLINE):
        csop.allow()
    ti = event.get("tool_input", {}) or {}
    fp = ti.get("file_path", "") or ti.get("notebook_path", "") or ""
    if not fp:
        csop.allow()
    cwd = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    msgs = []
    for t in _D.get("types") or []:
        if "match" not in t:
            msgs.append("malformed `types` entry, no `match` key: {0}".format(
                sorted(t.keys())))
            continue
        if not _match(fp, t.get("match")):
            continue
        if t.get("reminder"):
            msgs.append(t["reminder"].replace("{file}", fp))
        if t.get("command"):
            out = _run(t["command"].replace("{file}", fp), cwd)
            if out:
                msgs.append(out)
    if not msgs:
        csop.allow()
    csop.nudge("Filetypes ({0}) for `{1}`:\n{2}".format(
        DISCIPLINE, fp, "\n".join(msgs)), "PostToolUse")


if __name__ == "__main__":
    main()
