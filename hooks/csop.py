#!/usr/bin/env python3
"""csop -- the CSOP shared hook substrate + toggle CLI.

Domain-agnostic machinery for every gate and the CLI: fail-open event parsing,
project-level activation state, the `.claude/csop.json` override loader, the
`CSOP_<name>=off` escape hatch, and the enforcement primitives allow / block /
nudge / ask / deny. It knows nothing about specific disciplines, which are
singleton classes in `disciplines.py`.
"""
import fnmatch
import json
import os
import re
import sys


# ---- event -----------------------------------------------------------------

def load_event():
    try:
        return json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception:
        return {}


def session_id(event):
    return ((event or {}).get("session_id", "")
            or os.environ.get("CLAUDE_SESSION_ID", "")
            or "nosession")


# ---- state (which codenames are active) ------------------------------------

def _state_dir():
    return os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.join(
        os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()), ".claude", "csop-state")


def _state_path():
    """The active-discipline state file: project-level, never session-keyed. The
    CLI runs as Bash and so never receives CLAUDE_SESSION_ID, and a session key
    made the CLI and the hooks disagree. Sticky-latch semantics survive that
    because the SessionStart reset re-seeds this file on /clear."""
    return os.path.join(_state_dir(), "active.json")


def state_path(name):
    """Absolute path to an auxiliary state file `name` in the csop state dir
    (for gates that keep their own state alongside active.json)."""
    return os.path.join(_state_dir(), name)


def active():
    """The set of active discipline codenames (project-level)."""
    try:
        with open(_state_path()) as f:
            return set(json.load(f))
    except Exception:
        return set()


def is_active(codename):
    return codename in active()


def enable(codename):
    """Add an already-resolved codename to the active set."""
    os.makedirs(_state_dir(), exist_ok=True)
    cur = active()
    cur.add(codename)
    with open(_state_path(), "w") as f:
        json.dump(sorted(cur), f)
    return cur


def disable(codenames):
    """Drop already-resolved codenames from the active set, the inverse of enable.
    Disarming, so csop-gate-disarm keeps every agent-reachable route to it shut:
    only the human channel gets here (see docs/gate-internals.md)."""
    new = active() - set(codenames)
    reset(new)
    return new


def reset(codenames):
    """Set the active set to `codenames` (SessionStart seeds the default-enabled
    set, so /clear|startup re-seeds defaults rather than wiping to empty)."""
    os.makedirs(_state_dir(), exist_ok=True)
    with open(_state_path(), "w") as f:
        json.dump(sorted(codenames), f)


# ---- one-time notices (surfaced once by the Stop hook, then drained) --------

def push_notice(text):
    """Queue a one-time notice for the Stop hook (modeline) to surface once."""
    path = state_path("notices.json")
    try:
        data = json.load(open(path))
    except Exception:
        data = []
    if text not in data:
        data.append(text)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def drain_notices():
    """Return queued notices and clear them (shown at most once)."""
    path = state_path("notices.json")
    try:
        data = json.load(open(path))
    except Exception:
        data = []
    try:
        os.remove(path)
    except OSError:
        pass
    return data


def pend(key, text):
    """Hold `text` for a later hook in the same tool call, keyed by `key`. A
    PostToolUse hook cannot recover what a write added, since the file already
    holds it, so the PreToolUse side records it here."""
    path = state_path("pending.json")
    try:
        data = json.load(open(path))
    except Exception:
        data = {}
    data[key] = text
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def take(key):
    """Pop the value `pend` stored under `key`, or None."""
    path = state_path("pending.json")
    try:
        data = json.load(open(path))
    except Exception:
        return None
    val = data.pop(key, None)
    try:
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception:
        pass
    return val


# ---- project config override -----------------------------------------------

def _copy_string(text, i, out):
    """text[i] is a `"`; append the whole string literal to out; return new i."""
    out.append(text[i])
    i += 1
    n = len(text)
    while i < n:
        out.append(text[i])
        if text[i] == "\\" and i + 1 < n:
            out.append(text[i + 1])
            i += 2
            continue
        if text[i] == '"':
            return i + 1
        i += 1
    return i


def loads_jsonc(text):
    """Parse JSON with `//` + `/* */` comments and trailing commas (a practical
    JSON5 subset). stdlib-only, string-aware, two passes: strip comments, then
    strip trailing commas. (Full JSON5 -- single quotes, unquoted keys -- would
    need a vendored parser.)"""
    out, i, n = [], 0, len(text)           # pass 1: strip comments
    while i < n:
        c = text[i]
        if c == '"':
            i = _copy_string(text, i, out)
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    s = "".join(out)

    out, i, n = [], 0, len(s)              # pass 2: strip trailing commas
    while i < n:
        c = s[i]
        if c == '"':
            i = _copy_string(s, i, out)
            continue
        if c == ",":
            j = i + 1
            while j < n and s[j] in " \t\r\n":
                j += 1
            if j < n and s[j] in "}]":
                i += 1
                continue
        out.append(c)
        i += 1
    return json.loads("".join(out))


def project_config():
    """The project's `.claude/csop.json` override: a dict keyed by codename ->
    {param: value}; {} if absent or unparseable. Parsed as JSON-with-comments
    (see loads_jsonc). A discipline honors it only for its overridable params
    (see disciplines.py) -- identity/description live in code, never here."""
    proj = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    try:
        with open(os.path.join(proj, ".claude", "csop.json")) as f:
            return loads_jsonc(f.read())
    except Exception:
        return {}


# ---- stages (session-level current stage + per-stage policy) ---------------

def stages_config():
    """The top-level `stages` block from .claude/csop.json (a reserved key, not a
    codename): {name: {globs, from, disciplines, pre, post, default_stage}}. {} if
    absent or malformed."""
    cfg = project_config().get("stages")
    return cfg if isinstance(cfg, dict) else {}


def _stage_path():
    return state_path("stage.json")


def _stage_state():
    try:
        with open(_stage_path()) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def current_stage():
    """The session's current stage name, or None. A sticky latch: seeded from a
    stage's default_stage at SessionStart, changed by `csop.py stage <name>`."""
    return _stage_state().get("current")


def stage_history():
    """The stages that have been current this session, in first-seen order."""
    h = _stage_state().get("history")
    return h if isinstance(h, list) else []


def set_stage(name):
    """Make `name` the current stage and record it in the session history."""
    st = _stage_state()
    hist = st.get("history") if isinstance(st.get("history"), list) else []
    if name and name not in hist:
        hist.append(name)
    st["current"], st["history"] = name, hist
    os.makedirs(_state_dir(), exist_ok=True)
    with open(_stage_path(), "w") as f:
        json.dump(st, f)
    return name


def stage_pre_fired(name):
    """True if stage `name`'s `pre` prompt has already fired this session."""
    return name in (_stage_state().get("pre_fired") or [])


def mark_stage_pre(name):
    """Record that stage `name`'s `pre` prompt fired (dedup, once per session)."""
    st = _stage_state()
    pf = st.get("pre_fired") if isinstance(st.get("pre_fired"), list) else []
    if name not in pf:
        pf.append(name)
    st["pre_fired"] = pf
    os.makedirs(_state_dir(), exist_ok=True)
    with open(_stage_path(), "w") as f:
        json.dump(st, f)


def stage_successors(name):
    """Stages that list `name` as a `from` source: the forward edges out of `name`.
    One successor is the ladder case; several is a DAG branch."""
    return [s for s, cfg in stages_config().items()
            if isinstance(cfg, dict) and name in (cfg.get("from") or [])]


def default_stage():
    """The stage whose config sets default_stage true (first wins), or None."""
    for name, cfg in stages_config().items():
        if isinstance(cfg, dict) and cfg.get("default_stage"):
            return name
    return None


def seed_stage():
    """SessionStart: set the current stage to the configured default (or none)
    and start a fresh history."""
    os.makedirs(_state_dir(), exist_ok=True)
    d = default_stage()
    with open(_stage_path(), "w") as f:
        json.dump({"current": d, "history": [d] if d else []}, f)
    return d


def stage_of(path):
    """Advisory glob-membership: the first stage whose globs match `path` (config
    order), or None. Used for mismatch warnings and the from-DAG, never to pick the
    current stage."""
    p = (path or "").replace("\\", "/")
    if not p:
        return None
    for name, cfg in stages_config().items():
        globs = cfg.get("globs", []) if isinstance(cfg, dict) else []
        for g in globs or []:
            if fnmatch.fnmatch(p, g) or fnmatch.fnmatch(p, "*/" + g):
                return name
    return None


def _match_globs(path, globs):
    p = (path or "").replace("\\", "/")
    for g in globs or []:
        if fnmatch.fnmatch(p, g) or fnmatch.fnmatch(p, "*/" + g):
            return True
    return False


def _stage_ancestors(name, cfg, seen):
    for src in (cfg.get(name, {}) or {}).get("from", []) or []:
        if src not in seen:
            seen.add(src)
            _stage_ancestors(src, cfg, seen)
    return seen


def writable_globs(name):
    """The globs stage `name` may write: its explicit `writable` list if set, else
    the union of `globs` over the stage and its transitive `from` ancestors (the
    writable set grows as work is promoted up)."""
    cfg = stages_config()
    st = cfg.get(name) or {}
    if isinstance(st.get("writable"), list):
        return list(st["writable"])
    out = []
    for n in {name} | _stage_ancestors(name, cfg, set()):
        out += (cfg.get(n, {}) or {}).get("globs", []) or []
    return out


def writable_verdict(path):
    """For the current stage: "allow" when `path` is writable or unclassified,
    "deny" when it belongs to a stage outside the current stage's writable set.
    None when there is no current stage."""
    cs = current_stage()
    if not cs:
        return None
    if _match_globs(path, writable_globs(cs)):
        return "allow"
    if stage_of(path) is None:
        return "allow"                        # unclassified: out of scope
    return "deny"


def path_matches(path, globs):
    """True if `path` matches any glob, comparing repo-relative and absolute forms
    so an entry may be written either way. A leading `~` in a glob expands, which
    is how a user-level path outside the project is addressed."""
    p = os.path.abspath(os.path.expanduser(path or "")).replace("\\", "/")
    root = os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    rel = os.path.relpath(p, root).replace("\\", "/") if p.startswith(root) else p
    for g in globs or []:
        g = os.path.expanduser(g).replace("\\", "/")
        if _match_globs(rel, [g]) or _match_globs(p, [g]):
            return True
    return False


_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def oneline(text, limit=120):
    """Collapse `text` to a single sanitized line of at most `limit` characters.
    Stripping control bytes matters wherever the result joins styled output: a
    stray escape sequence in the source would otherwise scramble the whole block."""
    flat = _CONTROL.sub(" ", text or "").strip()
    flat = re.sub(r"\s+", " ", flat)
    return flat if len(flat) <= limit else flat[:max(0, limit - 1)].rstrip() + "…"


def write_target(tool, tool_input):
    """The file a write-family tool call targets, or "" for anything else."""
    ti = tool_input or {}
    if tool in ("Edit", "Write", "MultiEdit"):
        return ti.get("file_path", "") or ""
    if tool == "NotebookEdit":
        return ti.get("notebook_path", "") or ""
    return ""


def added_text(tool, tool_input, path="", subtract_prior=True):
    """The text a write-family call introduces: the new content of a Write, or the
    replacement side of each edit. Empty means the call only removes text, which is
    how a gate tells a retraction from an addition. A Write subtracts the file's
    current lines, which a PreToolUse caller wants and a PostToolUse one must turn
    off, since by then the file already holds what was written."""
    ti = tool_input or {}
    if tool == "Write":
        new = ti.get("content", "") or ""
        if not subtract_prior:
            return new
        old = ""
        p = path or ti.get("file_path", "") or ""
        if p and not os.path.isabs(p):
            p = os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()), p)
        try:
            with open(os.path.expanduser(p), encoding="utf-8", errors="replace") as f:
                old = f.read()
        except Exception:
            old = ""
        prior = set(old.splitlines())
        return "\n".join(ln for ln in new.splitlines() if ln.strip() and ln not in prior)
    if tool == "Edit":
        return ti.get("new_string", "") or ""
    if tool == "MultiEdit":
        return "\n".join(e.get("new_string", "") or "" for e in (ti.get("edits") or []))
    if tool == "NotebookEdit":
        return ti.get("new_source", "") or ""
    return ""


_DESC = re.compile(r"^\s*description:\s*(.+)$", re.MULTILINE)


def gist(text, limit=120):
    """A one-line summary of added memory text: the frontmatter `description`
    when the text carries one, else its first meaningful line."""
    m = _DESC.search(text or "")
    if m:
        return oneline(m.group(1), limit)
    for line in (text or "").splitlines():
        if line.strip() and line.strip() not in ("---",):
            return oneline(line, limit)
    return ""


_STAGE_DISABLE = ("false", "no", "disabled", "off")


def stage_discipline(codename):
    """The current stage's directive for `codename`: None (not mentioned), False
    (disable), or an overrides dict (enable, possibly empty). A dict enables and
    supplies per-stage config to merge; `true` or a non-disable string enables with
    no changes; `false`/`no`/`disabled`/`off`/`0` disable."""
    cs = current_stage()
    if not cs:
        return None
    disc = (stages_config().get(cs) or {}).get("disciplines", {}) or {}
    if codename not in disc:
        return None
    val = disc[codename]
    if isinstance(val, dict):
        return val
    if val is True:
        return {}
    if isinstance(val, str) and val.strip().lower() not in _STAGE_DISABLE:
        return {}
    return False


def effective_active():
    """The effective active set: session-enabled codenames, plus the current
    stage's enabled disciplines, minus its disabled ones. One source of truth so
    enforcement (gates) and awareness (nudge, modeline) agree on what is active.
    Note: a stage that toggles a discipline whose gate is not stage-aware
    (hacc/iso/freeze) changes only the awareness plane, not that gate."""
    base = set(active())
    cs = current_stage()
    if cs:
        for name in (stages_config().get(cs) or {}).get("disciplines", {}) or {}:
            d = stage_discipline(name)
            if d is False:
                base.discard(name)
            elif d is not None:
                base.add(name)
    return base


def effective(codename, default_action):
    """(active, action) for a discipline. `active` comes from effective_active();
    `action` is passed through by the caller from the now-stage-aware
    `Discipline.get("action")`, so no strength logic lives here."""
    return (codename in effective_active(), default_action)


# ---- shell parsing (shared substrate) --------------------------------------

_DESTRUCTIVE = re.compile(r"\b(rm|rmdir|mv|cp|shred|unlink)\b")
# every shell construct that writes a file without showing a diff, by name.
_WRITE_CONSTRUCTS = {
    "redirect": r">>?\s*(?!/dev/null|&)[^\s&|;<>]",
    "tee": r"\btee\b",
    "dd": r"\bdd\b",
    "truncate": r"\btruncate\b",
    "sed -i": r"\bsed\b[^|]*\s-i",
    "perl -i": r"\bperl\b[^|]*\s-i",
    "awk -i": r"\b(?:gawk|awk)\b[^|]*-i[\s'\"]*inplace",
    "patch": r"(?:^|[|;&]\s*)patch\b",
    "line editor": r"(?:^|[|;&]\s*)(?:ed|ex)\b",
    "install": r"(?:^|[|;&]\s*)install\b",
    "vcs patch": r"\bgit\b[^|]*\bapply\b",
}
_CREATORS = (r"\btouch\b", r"\bmkdir\b", r"\bchmod\b")
_INLINE_RUNTIME = re.compile(r"\b(?:python[0-9.]*|node|ruby|perl|php|deno|bun)\b[^|]*"
                             r"(?:\s-[ce]\b|\s-\s*<<)")
_INLINE_WRITE = re.compile(r"open\s*\([^)]*['\"](?:[wax]|r\+)[b+]*['\"]"
                           r"|write_text|writeFile|writelines?\s*\(|\.write\s*\("
                           r"|File\.(?:write|open)|fs\.(?:append|write)"
                           r"|shutil\.(?:copy|move)"
                           r"|os\.(?:replace|rename|remove|unlink)|Path\([^)]*\)\.write")


def destructive_verbs(command):
    """Filesystem-restructuring verbs present in a shell command, matched at a
    word boundary so `chmod` or `alarm` do not trip. Returns the sorted set of
    matched verbs, empty if none."""
    return sorted({m.group(1) for m in _DESTRUCTIVE.finditer(command or "")})


def write_constructs(command):
    """The named shell constructs in `command` that write a file in place, and so
    hide the change from a diff: a redirect or heredoc, an in-place editor, a
    patch, `install`, and an inline interpreter script that opens a file for
    writing. Returns the sorted set of names, empty if none."""
    cmd = command or ""
    found = {n for n, rx in _WRITE_CONSTRUCTS.items() if re.search(rx, cmd)}
    if _INLINE_RUNTIME.search(cmd) and _INLINE_WRITE.search(cmd):
        found.add("inline script")
    return sorted(found)


def mutates_files(command):
    """Whether a shell command touches the filesystem at all: a destructive verb,
    an in-place write, or a create. The broad question a gate asks when it cares
    that a path was written, not how."""
    cmd = command or ""
    return bool(destructive_verbs(cmd) or write_constructs(cmd)
                or any(re.search(rx, cmd) for rx in _CREATORS))


# ---- escape hatch ----------------------------------------------------------

def escaped(name):
    """True if the per-discipline escape hatch CSOP_<name>=off is set."""
    key = "CSOP_{0}".format(name.upper().replace("-", "_"))
    return os.environ.get(key, "").lower() in ("off", "0", "false")


# ---- enforcement primitives ------------------------------------------------

def allow():
    """Not-applicable / fail-open: let the tool call proceed."""
    sys.exit(0)


def block(message):
    """Hard block (PreToolUse): reject the tool call, message to Claude."""
    print(message, file=sys.stderr)
    sys.exit(2)


def nudge(text, event_name="PreToolUse"):
    """Soft nudge: allow the call but inject a reminder that reaches Claude."""
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": event_name, "additionalContext": text}}))
    print(text, file=sys.stderr)
    sys.exit(0)


def dropped(name, codename, bad):
    """Report unusable project config entries a gate discarded, then allow. A
    dropped rule never fires and looks exactly like one that did not match, so an
    inert gate would otherwise read as a passing one. Each item in `bad` says why
    that entry was unusable. Call on the allow path: a real finding outranks a
    config complaint."""
    if not bad:
        allow()
    nudge("{0} ({1}): dropped {2} unusable config entr{3} ({4}). Those rules are "
          "inert until .claude/csop.json is fixed.".format(
              name, codename, len(bad), "y" if len(bad) == 1 else "ies",
              "; ".join(bad)))


def _decide(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason}}))
    sys.exit(0)


def ask(reason):
    """Force a human confirmation prompt (sign-off). Can only add friction; a
    static deny rule still wins."""
    _decide("ask", reason)


def deny(reason):
    """Deny via the permission layer (reason shown in the permission UI)."""
    _decide("deny", reason)


def enforce(action, reason):
    """Dispatch to the primitive named by a discipline's `action` config:
    block | deny | ask | nudge. Unknown/blank -> block (the safe default)."""
    a = (action or "block").lower()
    if a == "nudge":
        nudge(reason)
    if a == "ask":
        ask(reason)
    if a == "deny":
        deny(reason)
    block(reason)


# ---- CLI: `csop.py enable <name|codename> | list | catalog` -----------------

def _new_nudges(before):
    """Nudge lines for disciplines that became active since the `before` snapshot
    of effective_active(). On a stage change this is what the new stage freshly
    activated. Returned for the CLI to print, so the /stage and /promote commands
    surface them to the user and the model (the pre-turn additionalContext nudge is
    model-facing and otherwise invisible)."""
    import disciplines
    gained = effective_active() - before
    out = []
    for d in disciplines.DISCIPLINES:
        if d.codename in gained and not escaped(d.codename):
            r = d.render("nudge")
            for item in (r if isinstance(r, list) else [r]):
                if item:
                    out.append("- " + item)
    return out


_USAGE = """csop.py <command>

  enable <name|codename>   activate a discipline for this session
  disable <name|all>       deactivate one, or every active discipline
  list                     the active disciplines (the no-argument default)
  catalog                  every discipline, with codename and description
  stage [<name>]           show the current stage, or make <name> current
  promote [<name>]         move to a successor stage along the `from` graph
  demote [<name>]          move back to a source stage
  help                     this text

Slash commands forward verbatim: /sop takes any of the above; /stage, /promote,
and /demote are shorthands for their verbs, as /sop-disable is for `disable`.
Disarming a discipline is human-only: run it from a slash command, never from
the agent's shell (see csop-gate-disarm)."""


def enable_drops(token):
    """What `enable <token>` would switch off: (direct, cascade) sets of currently
    active codenames, the conflicts of the enabled closure and everything that
    requires them. Non-empty means the enable is also a disarm, which is why
    csop-gate-disarm consults this before letting an agent run one."""
    import disciplines
    target = disciplines.closure({disciplines.resolve(token)})
    drop = set()
    for cn in target:
        drop |= disciplines.conflicts(cn)
    drop -= target
    cur = active()
    direct = cur & drop
    return direct, cur & disciplines.dependents(direct)


def disable_drops(token):
    """What `disable <token>` would switch off: the currently active codenames the
    token names, plus everything that requires them. `all` means the whole set."""
    import disciplines
    cur = active()
    if token.lower() == "all":
        return set(cur)
    rid = disciplines.resolve(token)
    return ({rid} | disciplines.dependents({rid})) & cur


def _cli(argv):
    if not argv:
        argv = ["list"]                 # no argument -> default to `list`
    import disciplines
    if argv[:1] == ["enable"] and len(argv) >= 2 and not argv[1].startswith("-"):
        rid = disciplines.resolve(argv[1])
        target = disciplines.closure({rid})
        direct, cascade = enable_drops(argv[1])
        removed = direct | cascade
        new = (active() | target) - removed
        reset(new)
        if removed:
            def _name(c):
                d = disciplines.by_codename(c)
                return d.name if d else c
            en = disciplines.by_codename(rid)
            msg = "{0} disabled {1} (conflict)".format(
                en.name if en else argv[1],
                ", ".join(sorted(_name(c) for c in direct)))
            if cascade:
                msg += ", and {0} (requires it)".format(
                    ", ".join(sorted(_name(c) for c in cascade)))
            push_notice(msg + ".")
        print("active: " + " ".join(sorted(new)))
        if removed:
            print("disabled: " + " ".join(sorted(removed)))
        return 0
    if argv[:1] == ["disable"] and len(argv) >= 2 and not argv[1].startswith("-"):
        removed = disable_drops(argv[1])
        if not removed:
            print("not active: {0}".format(argv[1]), file=sys.stderr)
            return 1
        new = disable(removed)
        print("active: " + " ".join(sorted(new)))
        print("disabled: " + " ".join(sorted(removed)))
        return 0
    if argv[:1] == ["stage"]:
        if len(argv) >= 2 and not argv[1].startswith("-"):
            name = argv[1]
            if name not in stages_config():
                print("unknown stage: {0} (defined: {1})".format(
                    name, " ".join(sorted(stages_config())) or "none"), file=sys.stderr)
                return 2
            before = effective_active()
            set_stage(name)
            print("stage: " + name)
            for ln in _new_nudges(before):
                print(ln)
            return 0
        names = list(stages_config().keys())
        print("stage: " + (current_stage() or "(none)"))
        print("available: " + (", ".join(names) if names else "(none defined)"))
        return 0
    if argv[:1] == ["promote"]:
        cur = current_stage()
        if not cur:
            print("no current stage; set one with `csop.py stage <name>`", file=sys.stderr)
            return 2
        succ = stage_successors(cur)
        if len(argv) >= 2 and not argv[1].startswith("-"):
            target = argv[1]
            if target not in succ:
                print("cannot promote {0} -> {1} (successors: {2})".format(
                    cur, target, ", ".join(succ) or "none"), file=sys.stderr)
                return 2
            before = effective_active()
            set_stage(target)
            print("promoted: {0} -> {1}".format(cur, target))
            for ln in _new_nudges(before):
                print(ln)
            return 0
        if not succ:
            print("already at the top: " + cur)
            return 0
        if len(succ) > 1:
            print("ambiguous: {0} promotes to any of {1}; pick with `csop.py stage <name>`".format(
                cur, ", ".join(succ)))
            return 0
        before = effective_active()
        set_stage(succ[0])
        print("promoted: {0} -> {1}".format(cur, succ[0]))
        for ln in _new_nudges(before):
            print(ln)
        return 0
    if argv[:1] == ["demote"]:
        cur = current_stage()
        if not cur:
            print("no current stage; set one with `csop.py stage <name>`", file=sys.stderr)
            return 2
        preds = (stages_config().get(cur) or {}).get("from") or []
        if len(argv) >= 2 and not argv[1].startswith("-"):
            target = argv[1]
            if target not in preds:
                print("cannot demote {0} -> {1} (sources: {2})".format(
                    cur, target, ", ".join(preds) or "none"), file=sys.stderr)
                return 2
            before = effective_active()
            set_stage(target)
            print("demoted: {0} -> {1}".format(cur, target))
            for ln in _new_nudges(before):
                print(ln)
            return 0
        if not preds:
            print("already at the bottom: " + cur)
            return 0
        if len(preds) > 1:
            print("ambiguous: {0} demotes to any of {1}; pick with `csop.py stage <name>`".format(
                cur, ", ".join(preds)))
            return 0
        before = effective_active()
        set_stage(preds[0])
        print("demoted: {0} -> {1}".format(cur, preds[0]))
        for ln in _new_nudges(before):
            print(ln)
        return 0
    if argv[:1] == ["list"]:
        print("active: " + " ".join(sorted(active())))
        return 0
    if argv[:1] == ["catalog"]:
        for d in disciplines.DISCIPLINES:
            req = " [requires: {0}]".format(" ".join(d.requires)) if d.requires else ""
            print("{0}  ({1}){2}  {3}".format(d.name, d.codename, req, d.description))
        return 0
    if argv[:1] in (["help"], ["-h"], ["--help"]):
        print(_USAGE)
        return 0
    print("unknown command: {0}\n{1}".format(" ".join(argv), _USAGE), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
