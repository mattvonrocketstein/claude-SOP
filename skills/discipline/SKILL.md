---
name: discipline
description: Awareness and management for CSOP process disciplines (SOPs). Invoke when enabling/listing disciplines or when working under one that is enabled, so the protocol stays in context all session.
---
# Disciplines (SOPs)

A **discipline** is a process-level protocol (a components of a SOP) which is enforced deterministically by hooks. Disciplines are **toggleable**: enable one per session. Each has a **name** (e.g.
`IsolatedTree`), a **description**, and a **codename** (e.g. `iso`).

## Managing disciplines

`/sop` forwards its arguments VERBATIM to the one CLI, so `/sop <args>` ≡
`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/csop.py" <args>`:

- `enable <name|codename>`: activate a discipline (e.g. `IsolatedTree` or `iso`).
- `list`: show active disciplines (also the no-arg default).
- `catalog`: list all known disciplines.
- Disarm all: `/clear`.

## Two halves of a discipline

- **Enforcement** -- PreToolUse gates that hard-block or soft-nudge. Deterministic.
- **Awareness** -- this skill body, which stays in context for the session so
  the protocol is followed proactively, not only when a gate trips.

## Bundled disciplines

<!-- TODO: one section per shipped discipline. Example below. -->

### IsolatedTree (codename `iso`)
When enabled, risky/experimental changes to a project's **core** must be
prototyped in an **iso-tree** (an isolated `git worktree` under a crash-safe,
in-repo, gitignored dir -- convention `scratch/iso/` -- never `/tmp`). The
`csop-gate-bashverb` hook blocks `git worktree add` targeting anywhere else.
