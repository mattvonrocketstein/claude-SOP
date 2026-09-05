#!/usr/bin/env python3
"""PreToolUse gate: Testing Discipline (codename `tdd`, and subclasses like `py-tdd`).

A Bash command that runs tests must carry a hypothesis in its description, or
`hypothesis_action` fires. A run that is not narrowed (no narrow regex, no
positional path outside `suite_roots`, no topic marker) is a suite run and fires
`action`, ask by default, so the human opts in. Fail-open; escape hatch CSOP_TDD=off.
"""
import glob
import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402

DISCIPLINE = disciplines.TestingDiscipline.codename
LAST_SRC = "tdd-last-src.json"

_HYPOTHESIS = ("Testing Discipline ({0}): no hypothesis, no test run. The call's "
               "description must say what you expect and what result would prove "
               "you wrong (it must match `{1}`). Restate it and rerun. "
               "(CSOP_TDD=off.)")
_SUITE = ("Testing Discipline ({0}): this is a full-suite run, which is the "
          "human's gate. Approve it, or narrow to one test, a file, the same-symbol "
          "grep hits, or a topic marker.{1}{2} If approved and it will take more "
          "than a few minutes, give an estimate, run it in the background, and "
          "report status. (CSOP_TDD=off.)")


def family():
    """Active members of the tdd family, most specific first."""
    if csop.escaped(DISCIPLINE):
        return []
    act = csop.effective_active()
    out = [d for d in disciplines.DISCIPLINES
           if issubclass(d, disciplines.TestingDiscipline)
           and d.codename in act and not csop.escaped(d.codename)]
    out.sort(key=lambda d: -len(d.__mro__))
    return out


def compiled(members, key, bad):
    out = []
    for d in members:
        for p in d.get(key) or []:
            try:
                out.append(re.compile(p))
            except Exception as e:
                bad.append("{0}.{1} {2!r}: {3}".format(d.codename, key, p, e))
    return out


def listed(members, key):
    out = []
    for d in members:
        for x in d.get(key) or []:
            if x not in out:
                out.append(x)
    return out


def _segments(cmd):
    return [s for s in re.split(r"\s*(?:&&|\|\||[;|])\s*", cmd) if s.strip()]


_WRAPPERS = ("time", "sudo", "nice", "env", "exec", "nohup", "xvfb-run")
_REDIRECT = re.compile(r"^(?:\d*[<>]{1,2}|&>)")


def _tokens(seg):
    try:
        return shlex.split(seg)
    except ValueError:
        return seg.split()


def _lead(seg):
    """The segment with leading env assignments and wrapper commands stripped."""
    toks = _tokens(seg)
    while toks and (re.match(r"^\w+=", toks[0]) or toks[0] in _WRAPPERS):
        toks.pop(0)
    if len(toks) > 1 and toks[0] == "timeout":
        toks = toks[2:]
    return toks


def _runs(toks, runners):
    """True when a runner regex matches at the command position of `toks`."""
    if not toks:
        return False
    text = " ".join(toks)
    return any(m and m.start() <= len(toks[0]) for m in (r.search(text) for r in runners))


def _args(toks, runners, value_opts):
    """(positionals, marker) after the runner token of one command segment."""
    start = next((i for i in range(len(toks))
                  if any(r.search(" ".join(toks[:i + 1])) for r in runners)), None)
    if start is None:
        return [], ""
    pos, marker, want = [], "", None
    for t in toks[start + 1:]:
        if want:
            if want == "-m":
                marker = t
            want = None
            continue
        if _REDIRECT.match(t):
            want = t if t in ("<", ">", ">>", "&>") else None
            continue
        if t in value_opts:
            want = t
            continue
        if t.startswith("-m="):
            marker = t[3:]
            continue
        if t.startswith("-"):
            continue
        pos.append(t)
    return pos, marker


def _scope(toks, members, runners, narrows):
    """suite | topic | narrow, for a segment already known to run tests."""
    seg = " ".join(toks)
    if any(p.search(seg) for p in narrows):
        return "narrow"
    roots = [os.path.normpath(r) for r in listed(members, "suite_roots")]
    pos, marker = _args(toks, runners, listed(members, "value_options"))
    if any(os.path.normpath(p) not in roots for p in pos):
        return "narrow"
    if marker:
        names = set(re.findall(r"\w+", marker))
        big = set(listed(members, "suite_markers"))
        return "suite" if names & big else "topic"
    return "suite"


def classify(cmd, members, bad=None):
    """(scope, segment) of the first test-running segment of `cmd`, or (None, '')."""
    bad = bad if bad is not None else []
    runners = compiled(members, "runner_patterns", bad)
    for d in members:
        tc = d.get("test_command")
        if tc:
            runners.append(re.compile(r"(?:^|[;&|]\s*)" + re.escape(tc) + r"\b"))
    narrows = compiled(members, "narrow_patterns", bad)
    for seg in _segments(cmd):
        toks = _lead(seg)
        if _runs(toks, runners):
            return _scope(toks, members, runners, narrows), seg
    return None, ""


def _suggest(members):
    """Test files named after the last edited source file, if any."""
    try:
        last = json.load(open(csop.state_path(LAST_SRC))).get("path", "")
    except Exception:
        return ""
    stem = os.path.splitext(os.path.basename(last))[0]
    if not stem:
        return ""
    proj = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    hits = []
    for g in listed(members, "test_globs"):
        for f in glob.glob(os.path.join(proj, g), recursive=True):
            if stem in os.path.basename(f) and "/scratch/" not in f:
                hits.append(os.path.relpath(f, proj))
    hits = sorted(set(hits))[:3]
    if not hits:
        return ""
    return " Last source edit was {0}; its tests: {1}.".format(
        os.path.relpath(last, proj) if os.path.isabs(last) else last,
        ", ".join("`{0}`".format(h) for h in hits))


def main():
    event = csop.load_event()
    if event.get("tool_name") != "Bash":
        csop.allow()
    members = family()
    if not members:
        csop.allow()
    ti = event.get("tool_input", {}) or {}
    cmd = ti.get("command", "") or ""
    bad = []
    scope, seg = classify(cmd, members, bad)
    if scope is None:
        csop.dropped("Testing Discipline", DISCIPLINE, bad) if bad else csop.allow()
    lead = members[0]
    label = lead.codename
    hyp = lead.get("hypothesis_pattern") or ""
    desc = ti.get("description", "") or ""
    if hyp and not re.search(hyp, desc, re.I):
        csop.enforce(lead.get("hypothesis_action"), _HYPOTHESIS.format(label, hyp))
    csop.pend("tdd:" + cmd, scope)
    if scope != "suite":
        csop.allow()
    example = lead.render("example") or ""
    ex = " Canonical form: `{0}`.".format(example) if example else ""
    csop.enforce(lead.get("action"), _SUITE.format(label, ex, _suggest(members)))


if __name__ == "__main__":
    main()
