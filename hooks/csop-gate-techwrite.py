#!/usr/bin/env python3
"""PreToolUse gate: Technical Writer (codename `techwrite`).

Checks an Edit / Write / MultiEdit against three rule sets on its added text:
`banned` substrings in any file, `prose_rules` in `prose_globs` documentation,
and prose-only `discouraged` words, which warn without ever blocking. Prose is
masked first so code regions are spared; see docs/gate-internals.md. Fail-open;
escape hatch CSOP_TECHWRITE=off.
"""
import fnmatch
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402

_TW = disciplines.TechnicalWriter
DISCIPLINE = _TW.codename
_JINJA = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.DOTALL)
_HTML = re.compile(r"<(script|style|pre|table|code)\b.*?</\1>", re.DOTALL | re.IGNORECASE)
_INLINE = re.compile(r"`+[^`\n]*`+")
_FENCE = re.compile(r"^\s*```")
_INDENT = re.compile(r"^(?: {4,}|\t)\S")
_BULLET = re.compile(r"^(?:[-*+#>]|\d+[.)])(?:\s|$)")


def _spaces(s):
    return re.sub(r"\S", " ", s)


def _blank(m):
    return _spaces(m.group(0))


def _indented_block(lines):
    """Which lines belong to an indented code block: a run indented four spaces
    or a tab, opened after a blank line. Covers a markdown indented block and an
    rst literal block or directive body alike, and skips a nested list item,
    which is indented but is prose."""
    out, blank, inblock = [False] * len(lines), True, False
    for i, ln in enumerate(lines):
        if not ln.strip():
            out[i], blank = inblock, True
            continue
        if _INDENT.match(ln) and (inblock or blank) and not _BULLET.match(ln.lstrip()):
            out[i] = inblock = True
        else:
            inblock = False
        blank = False
    return out


def _is_sep(line):
    s = line.strip().replace(" ", "")
    return bool(s) and set(s) <= set("|-:") and "-" in s and "|" in s


def _mask(text, mask_inline=True):
    text = _JINJA.sub(_blank, text)
    text = _HTML.sub(_blank, text)
    lines, infence = [], False
    for line in text.splitlines():
        if _FENCE.match(line):
            infence = not infence
            lines.append(_spaces(line))
        elif infence:
            lines.append(_spaces(line))
        else:
            lines.append(line)
    table = [False] * len(lines)
    for i, line in enumerate(lines):
        if _is_sep(line):
            table[i] = True
            j = i - 1
            while j >= 0 and "|" in lines[j]:
                table[j] = True
                j -= 1
            k = i + 1
            while k < len(lines) and "|" in lines[k]:
                table[k] = True
                k += 1
    block = _indented_block(lines)
    return [_spaces(ln) if table[i] or block[i]
            else (_INLINE.sub(_blank, ln) if mask_inline else ln)
            for i, ln in enumerate(lines)]


def _read(path):
    p = path or ""
    if not os.path.isabs(p):
        p = os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()), p)
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return None


def _new_old(tool, ti):
    if tool == "Write":
        return ti.get("content", "") or "", ""
    cur = _read(ti.get("file_path", ""))
    if cur is None:
        if tool == "Edit":
            return ti.get("new_string", "") or "", ti.get("old_string", "") or ""
        return "\n".join(e.get("new_string", "") or "" for e in ti.get("edits", []) or []), ""
    new = cur
    if tool == "Edit":
        new = cur.replace(ti.get("old_string", "") or "", ti.get("new_string", "") or "", 1)
    else:
        for e in ti.get("edits", []) or []:
            new = new.replace(e.get("old_string", "") or "", e.get("new_string", "") or "", 1)
    return new, cur


def _added(tool, ti):
    def diff(old, new):
        seen = set((old or "").splitlines())
        return [ln for ln in (new or "").splitlines() if ln not in seen]
    if tool == "Write":
        return diff("", ti.get("content", ""))
    if tool == "Edit":
        return diff(ti.get("old_string", ""), ti.get("new_string", ""))
    out = []
    for e in ti.get("edits", []) or []:
        out += diff(e.get("old_string", ""), e.get("new_string", ""))
    return out


def _prose(path):
    p = (path or "").replace("\\", "/").lower()
    if not p:
        return False
    for g in _TW.get("prose_globs") or []:
        gl = g.lower()
        if fnmatch.fnmatch(p, gl) or fnmatch.fnmatch(p, "*/" + gl):
            return True
    return False


def _word_rx(words):
    out = []
    for w in words or []:
        if w:
            out.append((w, re.compile(r"\b{0}(?:s|es)?\b".format(re.escape(w)),
                                      re.IGNORECASE)))
    return out


def _rules():
    """Compiled prose rules, plus a note per entry too broken to use."""
    out, bad = [], []
    for r in _TW.get("prose_rules") or []:
        if not isinstance(r, dict) or "pattern" not in r:
            bad.append("no `pattern` key: {0}".format(
                sorted(r) if isinstance(r, dict) else r))
            continue
        try:
            out.append((re.compile(r["pattern"]), r.get("message", "code in prose"),
                        bool(r.get("in_spans"))))
        except Exception as e:
            bad.append("bad regex {0}: {1}".format(r["pattern"], e))
    return out, bad


def main():
    event = csop.load_event()
    tool = event.get("tool_name", "")
    if tool not in ("Edit", "Write", "MultiEdit"):
        csop.allow()
    active, action = csop.effective(DISCIPLINE, _TW.get("action"))
    if not active or csop.escaped(DISCIPLINE):
        csop.allow()
    ti = event.get("tool_input", {}) or {}
    fp = ti.get("file_path", "")
    if os.path.basename(fp) in (_TW.get("exempt") or []):
        csop.allow()
    banned = [(b, b.lower()) for b in (_TW.get("banned") or []) if b]
    token = _TW.get("token") or ""
    soft = _word_rx(_TW.get("discouraged"))
    hits, warns, bad = [], [], []

    if _prose(fp):
        new, old = _new_old(tool, ti)
        seen = set(old.splitlines())
        raw = new.splitlines()
        masked = _mask(new, True)          # backtick spans blanked
        spans = _mask(new, False)          # backtick spans left intact (for in_spans rules)
        rules, bad = _rules()
        for i, line in enumerate(raw):
            if line in seen or (token and token in line):
                continue
            mfull = masked[i] if i < len(masked) else ""
            mspan = spans[i] if i < len(spans) else ""
            low = mfull.lower()
            for b, bl in banned:
                if bl in low:
                    hits.append(("banned `{0}`".format(b), mfull.strip()[:90]))
            for w, rx in soft:
                if rx.search(mfull):
                    warns.append(("discouraged `{0}`".format(w), mfull.strip()[:90]))
            for rx, msg, in_spans in rules:
                target = mspan if in_spans else mfull
                if rx.search(target):
                    hits.append((msg, target.strip()[:90]))
    else:
        for line in _added(tool, ti):
            if token and token in line:
                continue
            low = line.lower()
            for b, bl in banned:
                if bl in low:
                    hits.append(("banned `{0}`".format(b), line.strip()[:90]))

    if not hits and not warns:
        csop.dropped(_TW.name, DISCIPLINE, bad)

    def _fmt(items):
        out, seen = [], set()
        for why, snip in items:
            if (why, snip) in seen:
                continue
            seen.add((why, snip))
            out.append("  {0}: {1}".format(why, snip))
        return out

    lines = _fmt(hits)
    soft_lines = _fmt(warns)
    body = "\n".join(lines + soft_lines)
    tail = ("An em-dash reads as generated prose; keep runnable code in a fence or "
            "backticks, not in prose. Escape hatch: export CSOP_TECHWRITE=off.")
    if soft_lines:
        tail = ("A discouraged word is a warning only, never a block: reach for a "
                "plainer term unless the jargon is the subject.\n" + tail)
    msg = ("Technical Writer ({0}): {1} writing issue(s) in this edit.\n{2}\n\n{3}"
           ).format(DISCIPLINE, len(lines) + len(soft_lines), body, tail)
    if not lines:
        csop.nudge(msg)
    csop.enforce(action, msg)


if __name__ == "__main__":
    main()
