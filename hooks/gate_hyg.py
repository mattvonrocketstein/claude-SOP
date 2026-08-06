#!/usr/bin/env python3
"""PreToolUse gate: Generative Hygiene (codename `hyg`).

When `hyg` is active, reject an Edit/Write to a CODE file whose ADDED content:
  * adds a run of more than `max_comment_lines` comment lines (any indentation,
    common languages) -- externalizing chain-of-thought into code comments; or
  * puts CODE SYNTAX inside a comment (per the `syntax_rules` regex list) -- code,
    not prose.
The message pushes the reasoning into a notes/spike doc under `notes_dir`.

Only ADDED comment text is checked (Edit/MultiEdit diff old->new; Write scans the
whole content), so editing beside a grandfathered comment is fine. Prose/notes
files (.md/.rst/.txt, docs/, the notes_dir) are OUT of scope. Fail-open; escape
hatch CSOP_HYG=off. Enforcement strength = the discipline's `action`.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402

_HYG = disciplines.GenerativeHygiene
DISCIPLINE = _HYG.codename

# a full-line comment across common languages (first non-ws token is a marker).
_COMMENT_LINE = re.compile(r"^\s*(#|//|/\*|\*|--|;)")


def _comment_lines(text):
    return [ln for ln in (text or "").splitlines() if _COMMENT_LINE.match(ln)]


def _comment_runs(text):
    runs, run = [], []
    for ln in (text or "").splitlines():
        if _COMMENT_LINE.match(ln):
            run.append(ln)
        elif run:
            runs.append(run)
            run = []
    if run:
        runs.append(run)
    return runs


def _added(old_items, new_items):
    old = set(old_items)
    return [x for x in new_items if x not in old]


def _in_scope(path):
    p = (path or "").replace("\\", "/").lower()
    if not p:
        return False
    if p.rsplit(".", 1)[-1] in ("md", "markdown", "rst", "txt"):
        return False
    if "/docs/" in ("/" + p):
        return False
    nd = (_HYG.get("notes_dir") or "").strip("/").lower()
    if nd and (nd + "/") in (p + "/"):
        return False
    return True


def _rules():
    out = []
    for r in _HYG.get("syntax_rules"):
        try:
            out.append(re.compile(r))
        except Exception:
            pass
    return out


def _findings(old, new):
    out = []
    maxc = _HYG.get("max_comment_lines")
    old_runs = {"\n".join(r) for r in _comment_runs(old)}
    for run in _comment_runs(new):
        if "\n".join(run) not in old_runs and len(run) > maxc:
            out.append(("cot-in-comments",
                        "added a {0}-line comment block (max {1})".format(len(run), maxc),
                        run[0].strip()[:90]))
    rules = _rules()
    for ln in _added(_comment_lines(old), _comment_lines(new)):
        if any(rx.search(ln) for rx in rules):
            out.append(("syntax-in-comment",
                        "code syntax in a comment -- describe it in prose",
                        ln.strip()[:90]))
    return out


def main():
    event = csop.load_event()
    tool = event.get("tool_name", "")
    if tool not in ("Edit", "Write", "MultiEdit"):
        csop.allow()
    if not csop.is_active(DISCIPLINE) or csop.escaped(DISCIPLINE):
        csop.allow()
    ti = event.get("tool_input", {}) or {}
    if not _in_scope(ti.get("file_path", "")):
        csop.allow()
    try:
        findings = []
        if tool == "Write":
            findings = _findings("", ti.get("content", "") or "")
        elif tool == "Edit":
            findings = _findings(ti.get("old_string", ""), ti.get("new_string", "") or "")
        elif tool == "MultiEdit":
            for e in ti.get("edits", []) or []:
                findings += _findings(e.get("old_string", ""), e.get("new_string", "") or "")
    except Exception:
        csop.allow()                       # fail open
    if not findings:
        csop.allow()
    seen, lines = set(), []
    for name, why, snip in findings:
        if (name, snip) in seen:
            continue
        seen.add((name, snip))
        lines.append("  [{0}] {1}\n    > {2}".format(name, why, snip))
    msg = ("Generative Hygiene ({0}): {1} comment-hygiene issue(s) in this edit.\n"
           "{2}\n\nDon't externalize chain-of-thought into code comments (max {3} "
           "comment line(s) per block, no code syntax in comments). Put running "
           "notes / reasoning in a dedicated notes or spike doc under `{4}` "
           "instead. (Escape hatch: CSOP_HYG=off.)").format(
               DISCIPLINE, len(lines), "\n".join(lines),
               _HYG.get("max_comment_lines"), _HYG.get("notes_dir"))
    csop.enforce(_HYG.get("action"), msg)


if __name__ == "__main__":
    main()
