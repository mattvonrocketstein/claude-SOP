# CSOP

Claude-SOP, or, Standard Operating Procedures.

"For SOP Against Slop, choosey choosers choose CSOP."

Claude's *native* modes like *(plan | accept-edits | auto)* are a closed, built-in set.

A SOP is a group of active "disciplines", or, what you might call *user-space modes*.  

Note: this is a vibe-coded solution for vibe-coding problems, but hey.  Maybe it's better than nothing.  I mean.. probably it is better than *nothing*, right?!

## The Problem: Missing User Modes

Somehow it seems like hooks, skills, and plugins are working at this layer that is never quite right.  And once you start thinking about a *mode*, a few things click into place:

* Needing *one mode* implies many others
* Many modes implies the need to activate or deactivate *subsets* of modes
* Modes need overridable config per-mode and / or possibly per-project

**Modes aren't just prompted roles.**  Roles implies a bunch of prompts, but the whole point of retreating from CLAUDE.md is that Claude ignores instructions, will not remember project conventions.  **Everything needs gates, hooks, phases, protocols.**

Modes govern capabilities, but also suggest a kind of lifecycle beyond a turn and persist until disabled, etc, etc.  Good ideas!  But.. can you hook into Claude's existing mode and mode-lines?  **No you cannot.**  Who cares?  Uh, everyone.  There's a lot of possibilities between read-only and full auto.  

## Enter CSOP

With the real mode internals unavailable for extension, this plugin simulates it with structured groups of *permissions, hooks, pre-turn nudges, and post-turn status updates* to build something called a **discipline**. A group of active disciplines is a SOP, and `/csop` is the management tool.  This plugin can help to configure, activate, and deactivate progressive *layers* of agent restrictions, and nudging, and reminding.

Right, so the examples.  The most interesting stuff is *generalizing* a prompt-based role into something more like a *practice*.  Don't think *Scientist* or *Detective*, but something more like like *TDD*.

<!-- claude-list-disciplines-here -->
| Discipline | Codename | Default | Requires | Summary |
|---|---|---|---|---|
| **[IsolatedTree](#isolatedtree)** | `iso` | opt-in | — | Risky/exploratory/experimental changes to a project's core must be prototyped in an isolated git worktree (an 'iso-tree') under the crash-safe, in-repo, gitignored `dir` (default scratch/iso/), never /tmp. |
| **Human Accountability** | `hacc` | on | — | Git is read-only for the agent. |
| **Scratch** | `scratch` | on | — | Discourages/denies irreversibly destructive commands. |
| **Promotion** | `pro` | opt-in | — | Changes to CORE should be deliberate promotions of work proven in an iso-tree/scratch (small, tested, reviewable diffs), not ad-hoc edits. |
| **Generative Hygiene** | `hyg` | on | — | Comment hygiene on agent-generated code. |
| **[Frozen Features](#frozen-features)** | `freeze` | opt-in | — | Protects frozen paths and file regions from access. |
| **Test-Driven Development** | `tdd` | opt-in | — | Tests-first workflow. |
| **Feature Spike** | `spike` | opt-in | — | A time-boxed, throwaway exploratory spike to de-risk or learn. |
| **Performance** | `perf` | opt-in | — | Measure-first performance discipline. |
| **Tactical Retreat** | `tactical` | opt-in | — | When a change/experiment is going badly, cleanly retreat to a known-good state and rethink instead of accumulating hacks or churning flip/revert/flip. |
| **Dreamer** | `dream` | opt-in | — | Ideation / divergent-thinking mode. |
| **Scientist** | `science` | opt-in | — | Empirical / hypothesis-driven method. |
| **Stepwise** | `step` | opt-in | — | Small-increment method. |
| **Consensus** | `consensus` | opt-in | — | Corroboration / multi-perspective method. |
| **Groomer** | `groom` | opt-in | — | Incremental tidying / boy-scout-rule. |
| **Toolsmith** | `smith` | opt-in | — | Invest in tooling. |
| **Technical Writer** | `techwrite` | opt-in | `hyg` | Clear technical writing. |

## Disciplines

The table above is the quick reference; the deep dives below are added as
disciplines are ratified.

### IsolatedTree

`iso` · opt-in · enable with `/csop enable iso`

Prototype risky, exploratory, or experimental changes to core in a **throwaway git
worktree** — prove them against tests there, then port only the clean diff back —
so a failed experiment never touches core.

**Lifecycle**

<ul>
  <li><strong>Create a FRESH tree per task</strong> — <code>git worktree add scratch/iso/&lt;name&gt; &lt;clean-base&gt;</code>. One task, one tree.</li>
  <li><strong>Iterate and test inside the tree</strong> — commit WIP there freely; the tree is disposable.</li>
  <li><strong>Rebase onto core for freshness</strong> before promoting — <code>git -C scratch/iso/&lt;name&gt; rebase &lt;core&gt;</code> — so the diff reconciles against current core, not a stale base.</li>
  <li><strong>Promote by EDITS/INSERTS</strong> — hand-apply the proven diff into core files; never a git merge.</li>
  <li><strong>Discard the tree</strong> once the diff has landed.</li>
</ul>

**Enforced restrictions**

<ul>
  <li><strong>Location</strong> — a tree MUST live under <code>scratch/iso/</code> (crash-safe, in-repo, gitignored), never <code>/tmp</code>; a <code>git worktree add</code> elsewhere is blocked.</li>
  <li><strong>No reuse</strong> — the first write into a tree this session did not create fresh is blocked; a leftover tree is stale or WIP (unknown state), so work must not begin there.</li>
  <li><strong>Session-owned</strong> — only the session that created a tree may write into it.</li>
  <li><strong>Promotion is edits, not merges</strong> — under Human Accountability a git merge/commit into core is denied (a &ldquo;quiet commit&rdquo;); reconcile by editing core, and a human commits.</li>
  <li><strong>Sandbox git</strong> — history ops confined to a tree (rebase, commit) are allowed; ops that escape it (<code>push</code>/<code>pull</code>, <code>gc</code>/<code>prune</code>/<code>filter-*</code>) stay denied.</li>
  <li><strong>Reads are never gated</strong>; lift a step deliberately by exporting <code>CSOP_ISO=off</code> in your session.</li>
</ul>

**Config** (`.claude/csop.json`, project-overridable)

<ul>
  <li><code>dir</code> — where trees must live (default <code>scratch/iso/</code>).</li>
</ul>

### Frozen Features

`freeze` · opt-in · enable with `/csop enable freeze`

Protect stable or generated paths — and specific **regions inside a file** — from
edits. The discipline's `frozen` list is empty by default; a project fills it in
`.claude/csop.json`. Each entry is a bare path fragment, or a mapping for finer
control.

**What an entry can protect**

<ul>
  <li><strong>A whole file</strong> — a path fragment like <code>config/prod.yaml</code>.</li>
  <li><strong>A directory subtree</strong> — a fragment like <code>src/legacy/</code> (a &ldquo;section&rdquo; of the project).</li>
  <li><strong>A region inside a file</strong> — a mapping carrying <code>regex</code> and/or <code>prose</code> (below); the rest of the file stays editable.</li>
</ul>

**Whole-path modes**

<ul>
  <li><strong><code>no-write</code></strong> (default) — the path may be READ but not modified; Edit/Write/MultiEdit are blocked.</li>
  <li><strong><code>no-touch</code></strong> — READS are blocked too (Read/Grep/Glob and Bash references), for a generated/build-artifact copy where reading the stale copy is itself a trap; the message redirects to the entry's <code>use</code> (the real source).</li>
</ul>

**File regions**

<ul>
  <li><strong><code>regex</code> — a HARD gate.</strong> A pattern bracketing the protected span (e.g. <code>&lt;!-- FROZEN --&gt;.*&lt;!-- END --&gt;</code>). A write whose edited text overlaps a match is BLOCKED; edits elsewhere in the file pass. <code>.</code> matches across lines.</li>
  <li><strong><code>prose</code> — a soft NUDGE.</strong> A natural-language description of the region (e.g. &ldquo;the generated client stubs&rdquo;). Prose can't be located precisely, so any write to the file emits a one-time reminder rather than a block.</li>
  <li>An entry may carry both — <code>regex</code> enforces, <code>prose</code> explains.</li>
</ul>

**Enforcement**

<ul>
  <li>Whole-path and <code>regex</code> hits use the discipline's <code>action</code> (default <code>block</code>; also <code>deny</code> / <code>ask</code> / <code>nudge</code>).</li>
  <li><code>prose</code> regions are always a nudge — never a hard block.</li>
  <li>Reads are never gated except under <code>no-touch</code>.</li>
  <li>Escape hatch: export <code>CSOP_FREEZE=off</code> in your session for a deliberate, authorized change.</li>
</ul>

**Config** (`.claude/csop.json`, project-overridable)

<ul>
  <li><code>frozen</code> — the list of entries (paths and/or mappings); empty by default.</li>
  <li><code>mode</code> — default mode for a bare-path entry (<code>no-write</code>).</li>
  <li><code>action</code> — enforcement strength for hard hits.</li>
</ul>

```jsonc
"freeze": {
  "default_enabled": true,
  "frozen": [
    "src/legacy/",
    { "path": "build/_generated", "mode": "no-touch",
      "why": "materialized build artifact; regenerated at build time.", "use": "src/" },
    { "path": "config.py", "regex": "# FROZEN.*# END", "prose": "the credentials block" }
  ]
}
```

## Install

CSOP opts a project in as plain files wired through `${CLAUDE_PROJECT_DIR}`: no
marketplace, no plugin install, no manifest. Put a checkout somewhere in (or
reachable from) the project, then run `make install` from it. That writes the
hook wiring and the `/csop` commands into the project's `.claude/`. The code
lives in the checkout; state and config stay in the project
(`.claude/csop-state/`, `.claude/csop.json`).

### Submodule

The recommended way: the version is pinned and upgrades are a `git` command.

```bash
git submodule add https://github.com/mattvonrocketstein/claude-SOP tools/csop   # any path: .claude/csop, vendor/csop, ...
make -C tools/csop install
```

`make install` finds the checkout's path automatically, writes the project's
`.claude/settings.json` (hooks pointing back at the submodule), and materializes
the `/discipline`, `/csop`, and `/disc` commands. It never overwrites an existing
`settings.json`; if one is present it prints a note showing what to merge. Then:

- add `.claude/csop-state/` to the project's `.gitignore` (runtime state),
- start a Claude Code session in the project and approve workspace trust once.

The default-enabled disciplines (`hacc`, `scratch`, `hyg`) come on immediately;
opt into the rest with `/csop enable <name>`. Upgrade later with `git submodule
update --remote`; teammates run `git submodule update --init` after cloning.

### Without Submodule

Any checkout works the same way. Clone or copy the files anywhere and run the
same target:

```bash
git clone https://github.com/mattvonrocketstein/claude-SOP tools/csop     # or vendor the files in
make -C tools/csop install
```

If the checkout lives OUTSIDE the project (a shared install used by several
repos, where the git superproject can't be detected), point `make install` at
the project root:

```bash
make -C /path/to/csop install DEST=/path/to/your/project
```

Either way the result is identical: `.claude/settings.json` plus the commands are
written into the project, and each project keeps its own state and
`.claude/csop.json` overrides.

## Layout

```
.claude-plugin/
  plugin.json          # manifest: name/version + points at hooks.json  (schema: verify)
hooks/
  hooks.json           # wires SessionStart reset + PreToolUse gates + Stop umodeline
  csop.py              # substrate (state, escape-hatch, fail-open, enforce) + registry
                       #   + module-as-script CLI: enable <name|codename> | list | catalog
  session_reset.py     # SessionStart(clear|startup) -> wipe per-session state
  gate_bashverb.py     # archetype: hard-block a Bash verb unless a condition holds
  gate_softnudge.py    # archetype: one-time non-blocking nudge
  gate_pathblock.py    # archetype: hard-block access to protected paths
  umodeline.py         # Stop hook: print the active-discipline modeline each turn
commands/
  discipline.md        # /discipline slash command -> hooks/csop.py
skills/discipline/
  SKILL.md             # awareness half + management verbs
SPIKE-meta-disc.md     # design log / decisions / findings
```

## Modeline (umodeline)

A plugin cannot drive the built-in status line, so `umodeline.py` (a `Stop` hook)
falls back to printing a one-line footer of the active disciplines at the end of
each turn, e.g. `⬥ CSOP: iso`. Silent when nothing is active. It never blocks
(exits 0, guards on `stop_hook_active`), so it can't cause a continuation loop.

**Display channel.** Raw `Stop`-hook stdout is NOT shown to the user (confirmed);
the umodeline emits the documented user-visible **`systemMessage`** JSON field
(exit 0), which Claude Code renders as an end-of-turn notice.

## Runtime / dependencies

Hooks are **stdlib-only** by policy. A plugin has no runtime-dependency
mechanism: a hook is a command the harness runs through the host shell, using
whatever `python3` is on PATH — **no venv, no container, no install**. Because
these scripts import only the Python standard library, the only prerequisite is
a `python3` interpreter (near-universal, already assumed by Claude Code), so the
plugin works on a fresh machine with zero setup.

- Do NOT add third-party (`pip`) dependencies to hooks.
- Do NOT shell out to a container per gate — PreToolUse fires on ~every tool
  call, so container startup cost is prohibitive.
- If a future discipline truly needs a heavy dependency: vendor a pure-Python
  package onto `sys.path`, or bootstrap a venv in `${CLAUDE_PLUGIN_DATA}` from a
  SessionStart hook. Never a container-per-call.
- No `python3` on PATH → hooks fail-open (tool proceeds, discipline off).
