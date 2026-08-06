#!/usr/bin/env python3
"""csop -- the CSOP shared hook substrate + toggle CLI.

Domain-agnostic machinery used by every discipline gate and the CLI:
  * event parsing that FAILS OPEN (a bug here can never brick a tool call)
  * project-level activation STATE (which discipline CODENAMES are active) in a
    single active.json under ${CLAUDE_PLUGIN_DATA} or .claude/csop-state
  * the project CONFIG-override loader (.claude/csop.json)
  * the escape-hatch convention (CSOP_<NAME>=off)
  * enforcement primitives: allow / block / nudge / ask / deny

This file knows NOTHING about specific disciplines -- those are singleton
classes in `disciplines.py` (identity + default properties in code). csop only
handles activation state, the config-override file, and the enforce protocol.
"""
import json
import os
import sys


# ---- event -----------------------------------------------------------------

def load_event():
    try:
        return json.load(sys.stdin)
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
    # ONE project-level file, NOT session-keyed: the CLI (run by the model via
    # Bash) doesn't receive CLAUDE_SESSION_ID, so a session key made the CLI and
    # the hooks disagree. "Active until /clear" is preserved by the SessionStart
    # reset re-seeding this file, not by keying on the session.
    return os.path.join(_state_dir(), "active.json")


def state_path(name):
    """Absolute path to an auxiliary state file `name` in the csop state dir
    (for gates that keep their own state alongside active.json)."""
    return os.path.join(_state_dir(), name)


def active():
    """The set of active discipline CODENAMES (project-level)."""
    try:
        with open(_state_path()) as f:
            return set(json.load(f))
    except Exception:
        return set()


def is_active(codename):
    return codename in active()


def enable(codename):
    """Add an already-resolved CODENAME to the active set."""
    os.makedirs(_state_dir(), exist_ok=True)
    cur = active()
    cur.add(codename)
    with open(_state_path(), "w") as f:
        json.dump(sorted(cur), f)
    return cur


def reset(codenames):
    """Set the active set to `codenames` (SessionStart seeds the default-enabled
    set, so /clear|startup re-seeds defaults rather than wiping to empty)."""
    os.makedirs(_state_dir(), exist_ok=True)
    with open(_state_path(), "w") as f:
        json.dump(sorted(codenames), f)


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
    (see loads_jsonc). A discipline honors it only for its OVERRIDABLE params
    (see disciplines.py) -- identity/description live in code, never here."""
    proj = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    try:
        with open(os.path.join(proj, ".claude", "csop.json")) as f:
            return loads_jsonc(f.read())
    except Exception:
        return {}


# ---- escape hatch ----------------------------------------------------------

def escaped(name):
    """True if the per-discipline escape hatch CSOP_<NAME>=off is set."""
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


def _decide(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason}}))
    sys.exit(0)


def ask(reason):
    """Force a HUMAN confirmation prompt (sign-off). Can only ADD friction; a
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


# ---- CLI (module-as-script; disciplines imported lazily to avoid a cycle) ---
#   python3 csop.py enable <name|codename> | list | catalog

def _cli(argv):
    if not argv:
        argv = ["list"]                 # no argument -> default to `list`
    import disciplines
    if argv[:1] == ["enable"] and len(argv) >= 2 and not argv[1].startswith("-"):
        cur = active()
        for cn in sorted(disciplines.closure({disciplines.resolve(argv[1])})):
            cur = enable(cn)
        print("active: " + " ".join(sorted(cur)))
        return 0
    if argv[:1] == ["list"]:
        print("active: " + " ".join(sorted(active())))
        return 0
    if argv[:1] == ["catalog"]:
        for d in disciplines.DISCIPLINES:
            req = " [requires: {0}]".format(" ".join(d.requires)) if d.requires else ""
            print("{0}  ({1}){2}  {3}".format(d.name, d.codename, req, d.description))
        return 0
    print("usage: csop.py (enable <name|codename> | list | catalog)",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
