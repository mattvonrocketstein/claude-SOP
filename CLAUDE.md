# CSOP

CSOP (`csop` in code/filenames/env, **CSOP** in prose; repo `claude-SOP`) is a
Claude Code **plugin** that creates and manages *multiple* **disciplines**:
toggleable, hook-enforced process protocols (SOPs). This repo is **self-hosting**:
its own gates are wired into `.claude/settings.json`, so CSOP disciplines apply
while working here. Run **`make init`** once to complete setup (it validates the
plugin and materializes the `/discipline` `/csop` `/disc` command surface under
`.claude/commands/`); **`make check`** smoke-tests the hooks + CLI offline;
**`make help`** lists targets.

SSOT for design, decisions, and findings is `SPIKE-meta-disc.md`. Read it before
any substantial change.

## What things are

- **discipline**: a process protocol with a **name** (e.g. `IsolatedTree`), a
  **description**, and a **codename** (e.g. `iso`; defaults to the slugified name).
  Toggleable, pure opt-in, enabled per session.
- **gate**: a PreToolUse hook that enforces a discipline (hard-block `exit 2`, or
  soft-nudge `exit 0` + additionalContext). Fails OPEN on error.
- The **codename keys everything** (state + gates). Roster is `csop.json`.

## Managing disciplines (self-hosted here)

`/discipline`, aliased **`/csop`** and **`/disc`**, forwards its arguments VERBATIM
to the one CLI, so `/csop <args>` is equivalent to `python3 hooks/csop.py <args>`:

- `enable <name|codename>` (e.g. `IsolatedTree` or `iso`).
- `list` (also the no-arg default), `catalog`.
- `disable <name|all>`, human-only: `/csop-disable` is the human's command, and
  `csop-gate-disarm.py` blocks every route an agent has to a smaller active set.
  Never try to disarm a discipline; ask the human to run it.
- `/clear` disarms everything (SessionStart reset wipes state).

A slash command is always one model turn (a brief pause), even though the CLI is
instant -- the `!`-prefixed command body makes it a single deterministic relay,
the fastest a `/command` can be.

`IsolatedTree` (`iso`) applies to THIS repo too: prototype risky changes to the
plugin's own code in an iso-tree under `scratch/iso/` (never `/tmp`); arm it with
`/csop enable iso`.

## Conventions (hold the line on these)

- **stdlib-only hooks.** No pip deps, no venv, no container-per-gate. `python3` is
  the only prerequisite (PreToolUse fires per tool call: gates must be instant and
  zero-install).
- **One implementation, many entry points.** All logic lives in `hooks/csop.py`
  (importable API for gates + module-as-script CLI). NO `bin/`, NO bash mirror. The
  `/discipline|/csop|/disc` commands are pure forwarders; they must never
  reinterpret arguments or diverge from the CLI.
- **Gates fail open and consult state** (enforce only when their discipline is
  active).
- **No package/`__main__.py`** until `csop.py` outgrows one file; it is invoked by
  path, never `python -m`.
- Prose states concepts; put code symbols in code. Keep CLAUDE.md and README lean.

## Testing hooks

Hooks read a JSON event on stdin, so test OFFLINE with synthetic events (no live
session needed):

    export CLAUDE_PLUGIN_DATA=$(mktemp -d) CLAUDE_SESSION_ID=t
    python3 hooks/csop.py enable iso
    printf '%s' '{"session_id":"t","tool_name":"Bash","tool_input":{"command":"git worktree add /tmp/x HEAD"}}' | python3 hooks/csop-gate-bashverb.py   # -> exit 2

Verify in batches (parse, JSON-validate, one lifecycle smoke test), not per-edit.

## Boundaries (verified, detail in SPIKE)

- Plugins cannot set the status line via the plugin manifest, but a `statusLine`
  entry works, CLI-only (confirmed absent in the desktop app on a genuine cold
  start): see README's "Status line" section for the opt-in snippet and why it's
  never auto-wired into a shared, committed `settings.json`.
- Claude's permission modes are a closed set: disciplines are "user-space modes"
  built on hooks.
- Plugins cannot observe ctrl-c/interrupts: never rely on hooks for critical
  cleanup; reset rides `SessionStart`.

## Open / unverified

- `plugin.json` + `hooks.json` schema and the `${CLAUDE_PLUGIN_ROOT}` path var:
  verify against current plugin docs before treating this as a real installable
  plugin. (Self-hosting here uses `.claude/settings.json` with `${CLAUDE_PROJECT_DIR}`,
  which sidesteps that until verified.)
- `statusLine` rendering in the web app: untested.
