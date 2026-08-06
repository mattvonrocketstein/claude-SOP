#!/usr/bin/env python3
"""PreToolUse gate: Generative Hygiene (codename `hyg`).

Rejects an Edit/Write to a code file whose added text over-runs a comment budget,
puts code syntax (per `syntax_rules`) in a comment, or shouts a bare all-caps
word. Code comments get `max_comment_lines`, documentation gets the larger
`doc_max_comment_lines`, and a block is judged at its resulting size. Counting
rules and scope: docs/gate-internals.md. Fail-open; escape hatch CSOP_HYG=off.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402

_HYG = disciplines.GenerativeHygiene
DISCIPLINE = _HYG.codename

_MARKER_CACHE = {}
# a shouted word is a bare all-caps run; underscore/digit tokens pass whole.
_WORD = re.compile(r"[A-Za-z0-9_]+")
_SHOUT = re.compile(r"[A-Z]{2,}")
# a block-comment continuation line, ambiguous when the region state is unknown.
_CONT = re.compile(r"^\s*\*")
# a rule of repeated punctuation: a banner is structure, never narration.
_BANNER = re.compile(r"^[^\w\n]*[-=*_~+#]{3,}")


def _markers(file_path):
    """The line-comment markers for this file, keyed on extension (or on the
    lowercased basename when there is none). A file type the table does not name
    falls back to `unknown_markers`; a type mapped to an empty list, such as CSS,
    has no line comment at all, so `#header` is a selector rather than a comment."""
    base = os.path.basename((file_path or "").replace("\\", "/")).lower()
    ext = base.rsplit(".", 1)[-1] if "." in base else base
    table = _HYG.get("comment_markers") or {}
    return table.get(ext, _HYG.get("unknown_markers") or [])


def _line_rx(markers):
    """A matcher for a full-line comment in a file with these markers."""
    key = tuple(markers)
    if key not in _MARKER_CACHE:
        alts = "|".join(re.escape(m) for m in markers)
        _MARKER_CACHE[key] = re.compile(r"^\s*(?:{0})".format(alts)) if alts else None
    return _MARKER_CACHE[key]


def _region_specs():
    specs = []
    for r in _HYG.get("doc_regions") or []:
        try:
            specs.append((re.compile(r["open"]), re.compile(r["close"])))
        except Exception:
            pass
    return specs


def _scan(text, state=None, markers=None):
    """Classify each line as code, comment, or doc, carrying any open-region
    state so a later chunk can resume. A `doc` line is documentation by its
    marker: a `doc_prefixes` line or a line inside a `doc_regions` region. Marker
    shape is the only test, because where a doc block sits relative to what it
    documents is language-specific, and this gate is not."""
    prefixes = _HYG.get("doc_prefixes") or []
    specs = _region_specs()
    line_rx = _line_rx(_HYG.get("unknown_markers") or []
                       if markers is None else markers)
    out = []
    for ln in (text or "").splitlines():
        if state is not None:
            out.append((ln, "doc", state))
            if specs[state][1].search(ln):
                state = None
            continue
        stripped = ln.lstrip()
        if any(stripped.startswith(p) for p in prefixes):
            out.append((ln, "doc", None))
            continue
        opened = None
        if not (line_rx and line_rx.match(ln)):
            for i, (open_rx, close_rx) in enumerate(specs):
                m = open_rx.match(ln)
                if m:
                    opened = i
                    out.append((ln, "doc", i))
                    state = None if close_rx.search(ln, m.end()) else i
                    break
        if opened is None:
            comment = bool(line_rx and line_rx.match(ln))
            out.append((ln, "comment" if comment else "code", None))
    return out, state


def _banner(line, markers):
    """A section banner: a comment whose body is a rule of repeated punctuation."""
    body = line.strip()
    for m in sorted(markers or [], key=len, reverse=True):
        if body.startswith(m):
            body = body[len(m):]
            break
    return bool(_BANNER.match(body))


def _comment_lines(text, state=None, markers=None):
    mk = (_HYG.get("unknown_markers") or []) if markers is None else markers
    lines, _ = _scan(text, state, markers)
    return [ln for ln, kind, _ in lines
            if kind == "comment" and not _banner(ln, mk)]


def _prose_lines(text, state=None, markers=None):
    lines, _ = _scan(text, state, markers)
    return [ln for ln, kind, _ in lines if kind in ("comment", "doc")]


def _comment_runs(text, state=None, markers=None):
    lines, _ = _scan(text, state, markers)
    runs, run, run_kind = [], [], None
    markers = (_HYG.get("unknown_markers") or []) if markers is None else markers
    for ln, kind, _ in lines:
        if kind == "comment" and _banner(ln, markers):
            kind = "code"
        if kind in ("comment", "doc"):
            if run and kind != run_kind:
                runs.append((run_kind, run))
                run = []
            run_kind = kind
            run.append(ln)
        elif run:
            runs.append((run_kind, run))
            run = []
    if run:
        runs.append((run_kind, run))
    return runs


def _resolve(file_path):
    p = file_path or ""
    if p and not os.path.isabs(p):
        p = os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()), p)
    return p


def _region_state_before(file_path, old_string):
    """The doc-region state the edit lands in, as (state, known)."""
    if not old_string:
        return None, False
    content = _read_file(file_path)
    if content is None:
        return None, False
    idx = content.find(old_string)
    if idx < 0:
        return None, False
    _, state = _scan(content[:idx], None, _markers(file_path))
    return state, True


def _words(run):
    return len([ln for ln in run if _WORD.search(ln)])


def _whole(tool, ti):
    """The file's content before and after this edit, or None when it cannot be
    reconstructed. Judging the resulting block rather than the diff fragment is
    what stops a block being grown past its budget one small append at a time."""
    cur = _read_file(ti.get("file_path", ""))
    if cur is None:
        return None
    edits = ([ti] if tool == "Edit" else ti.get("edits", []) or [])
    new = cur
    for e in edits:
        old = e.get("old_string", "") or ""
        if not old or old not in new:
            return None
        new = new.replace(old, e.get("new_string", "") or "", 1)
    return cur, new


def _read_file(file_path):
    try:
        with open(_resolve(file_path)) as f:
            return f.read()
    except Exception:
        return None


def _added(old_items, new_items):
    old = set(old_items)
    return [x for x in new_items if x not in old]


def _in_scope(path):
    p = (path or "").replace("\\", "/").lower()
    if not p:
        return False
    if p.rsplit(".", 1)[-1] in [x.lower().lstrip(".") for x in _HYG.get("prose_exts") or []]:
        return False
    for d in _HYG.get("prose_dirs") or []:
        if ("/" + d.strip("/").lower() + "/") in ("/" + p):
            return False
    iso = (disciplines.IsoTree.get("home") or "").strip("/").lower()
    if iso and (iso + "/") in (p + "/"):
        return True                        # iso trees hold code bound for core; enforce here
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


def _findings(old, new, state=None, known=True, markers=None):
    out = []
    maxc = _HYG.get("max_comment_lines")
    docmax = _HYG.get("doc_max_comment_lines")
    old_runs = _comment_runs(old, state, markers)
    for kind, run in _comment_runs(new, state, markers):
        doc = kind == "doc" or (
            not known and all(_CONT.match(ln) for ln in run))
        budget = docmax if doc else maxc
        size = _words(run)
        if size <= budget:
            continue
        shared = set(run)
        prior = [r for _, r in old_runs if shared & set(r)]
        was = max([_words(r) for r in prior] or [0])
        if size <= was:
            continue                       # already this long: shrink it or leave it, but do not grow it
        label = "documentation" if doc else "comment"
        seen = set().union(*[set(r) for r in prior]) if prior else set()
        fresh = [ln for ln in run if ln not in seen and ln.strip()]
        why = ("grew a {0} block from {1} to {2} lines (max {3}): trim it, do not "
               "extend it".format(label, was, size, budget) if was else
               "added a {0}-line {1} block (max {2})".format(size, label, budget))
        out.append(("cot-in-comments", why,
                    (fresh[0] if fresh else run[0]).strip()[:90]))
    rules = _rules()
    shout_ok = set(_HYG.get("shout_ok") or [])
    for ln in _added(_comment_lines(old, state, markers),
                     _comment_lines(new, state, markers)):
        if any(rx.search(ln) for rx in rules):
            out.append(("syntax-in-comment",
                        "code syntax in a comment -- describe it in prose",
                        ln.strip()[:90]))
    for ln in _added(_prose_lines(old, state, markers),
                     _prose_lines(new, state, markers)):
        for w in _WORD.findall(ln):
            if _SHOUT.fullmatch(w) and w not in shout_ok:
                out.append(("shout-in-comment",
                            "shouted word `{0}`: we don't shout for emphasis (a "
                            "real global or env-var is fine, it keeps its "
                            "underscores; else add it to shout_ok)".format(w),
                            ln.strip()[:90]))
                break
    return out


def main():
    event = csop.load_event()
    tool = event.get("tool_name", "")
    if tool not in ("Edit", "Write", "MultiEdit"):
        csop.allow()
    active, action = csop.effective(DISCIPLINE, _HYG.get("action"))
    if not active or csop.escaped(DISCIPLINE):
        csop.allow()
    ti = event.get("tool_input", {}) or {}
    if not _in_scope(ti.get("file_path", "")):
        csop.allow()
    try:
        findings = []
        fp = ti.get("file_path", "")
        mk = _markers(fp)
        if tool == "Write":
            findings = _findings("", ti.get("content", "") or "", markers=mk)
        else:
            whole = _whole(tool, ti)
            if whole is not None:
                findings = _findings(whole[0], whole[1], markers=mk)
            elif tool == "Edit":
                old = ti.get("old_string", "")
                state, known = _region_state_before(fp, old)
                findings = _findings(old, ti.get("new_string", "") or "",
                                     state, known, mk)
            else:
                for e in ti.get("edits", []) or []:
                    old = e.get("old_string", "")
                    state, known = _region_state_before(fp, old)
                    findings += _findings(old, e.get("new_string", "") or "",
                                          state, known, mk)
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
    kinds = {name for name, _, _ in findings}
    tail = []
    if "cot-in-comments" in kinds:
        tail.append("Budgets: {0} comment line(s) per block, {1} in a documentation "
                    "block. Say it once and shorter, or move the reasoning to a notes "
                    "or spike doc under `{2}`.".format(
                        _HYG.get("max_comment_lines"),
                        _HYG.get("doc_max_comment_lines"), _HYG.get("notes_dir")))
    if "syntax-in-comment" in kinds:
        tail.append("Describe code in prose rather than quoting its syntax.")
    if "shout-in-comment" in kinds:
        tail.append("Drop the all-caps emphasis, or add a real acronym to shout_ok.")
    tail.append("Escape hatch: CSOP_HYG=off.")
    msg = ("Generative Hygiene ({0}): {1} comment-hygiene issue(s) in this edit.\n"
           "{2}\n\n{3}").format(DISCIPLINE, len(lines), "\n".join(lines),
                                 " ".join(tail))
    csop.enforce(action, msg)


if __name__ == "__main__":
    main()
