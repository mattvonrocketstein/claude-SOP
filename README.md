# CSOP

Claude-SOP, or, Standard Operating Procedures.

"For SOP Against Slop, choosey choosers choose CSOP."

Claude's *native* modes like *(plan | accept-edits | auto)* are a closed, built-in set.

A SOP is a group of active "disciplines", or, what you might call *user-space modes*.

Yup, a real person writes *most* of these docs, and curates the rest.  Be advised however that this is *definitely* a vibe-coded solution for vibe-coding problems.  I mean, come on, it is probably better than *nothing*, right?  Right?!

**Quick Links:** [The Problem](#the-problem-missing-user-modes) | [Enter CSOP](#enter-csop) | [Compare And Contrast](#compare-and-contrast) | [Examples](#examples) | [Install](#install) | [The Disciplines](#the-disciplines) | [Configuration Layering](#configuration-layering) | [Layout](#layout) | [Abstractions](#abstractions) | [Misc Notes](#misc-notes)

## The Problem: Missing User Modes

Hooks, skills, and plugins are always working at this layer that is never quite right.  And once you start thinking about a *mode*, a few things click into place:

* Needing one mode implies many others
* Many modes implies the need to activate or deactivate *subsets* of modes
* Modes need overridable config per-mode and / or possibly per-project

**Modes are not prompted roles,** or at least not *only* that.  The whole point of retreating from pretty-please prompting is that AI ignores instructions, will never permanently remember project conventions if they differ substantially from training, and all of this only gets worse as the weight of context increases.  Repeated nudging helps but isn't reliable.. **Everything needs gates, hooks, phases, protocols.**

Modes govern capabilities, but also suggest a kind of lifecycle beyond a turn and something that persists until disabled, etc, etc.  Good ideas!  But.. can you hook into Claude's existing mode?  **Not really.** Hooking just the status line works in newer CLI versions, but not in the app.  And the status-line, which we need to know what modes are active at any given time, is only a piece of the puzzle.

Anyway.. who cares?  Everyone should!  There's a lot of possibilities between read-only and full auto.

**What about Agents?**  Subagents (`.claude/agents/*.md`) are the closest *native* thing to a user-defined mode.  They provide a name, a system prompt, a blessed `tools:` list.  Still a role though and not yet a mode!  It's the granularity/layer problem again.  Tools-governance here is a coarse allow-list.. it can say "no Bash", but not "Bash *only for `tox`*".  An agent is a *delegate you spawn for a task*, not a persistent constraint that could hard-block your next tool call, and as a glorified prompt, there's little room for determinism, or CI-style progressive guarantees / ratcheting gates.  More on that later.

## Enter CSOP

With Claude's real mode internals unavailable for extension, this plugin fakes it by using everything else that *is* available, and allows for configuring, activating, and deactivating progressive *layers* of restrictions.

* **A Discipline** is a structured group of *permissions, prompts, hooks, pre-turn nudges, and post-turn reminders*.

* **A SOP** is a group of active disciplines, and `/csop` is the management tool.  

* **A Stage** is a named entry and associated configuration block.  There are potentially many stages, but typically 1 active at a time.  Config can activate, deactivate, or extend active SOP(s), basically allowing for override of per-discipline defaults.  Stages might be arranged into DAGs, but can also just be user-activated via `/stage ..`.

Current stage and active-disciplines are displayed in the user modeline:

<img src="docs/img/csop-modeline-app.png" alt="CSOP modeline showing active stage and disciplines">
<img src="docs/img/csop-modeline-cli.png" alt="CSOP modeline in the CLI">

## Compare And Contrast

With definitions in hand, back to Claude's built-in agents for a second.  Those *can't be* a discipline.  But disciplines do *compose* with agents, since hooks fire *inside* subagents too.  A discipline then is.. basically the deterministic foundation any agent runs on, regardless of the rest of the prompts that are in play.

If the whole *stage* thing sounds like reinventing CI/CD, well yeah, wouldn't it be nice to avoid this?  Some people might like the idea of bolting on *actual CI* and a whole evented subsystem for this sort of thing better.  Sounds fun! But again it's likely to hit that layer/granularity mismatch thing, e.g. a post-commit vs a pre-edit hook is quite a different thing, and sometimes you can't just compromise here and accept problems "temporarily" to be corrected "later, maybe, if token budget permits".  If you propose to manage a swarm autonomously, you may want to start with effectively steering something small interactively.

## Examples

NB: List is incomplete.  Lots of in-flight WIP and experiments in the repo, so the stuff here is just the things that are starting to feel more stable and definitely worthwhile.

| Discipline | Codename | Default | Code | Summary |
|---|---|---|---|---|
| **[Human Accountability](#human-accountability)** | `hacc` | on | [code](hooks/csop-gate-git.py) | Git is read-only for the agent. |
| **[Robot Accountability](#robot-accountability)** | `racc` | on with `hyg` | [code](hooks/csop-gate-racc.py) | The robot counterpart to Human Accountability: file changes go through the Edit/Write tool (a visible diff), not in-place shell mutations. |
| **[Memory Accountability](#memory-accountability)** | `mem` | opt-in | [code](hooks/csop-gate-mem.py) | Memory formation is a human decision: a write to a memory path asks first, is denied, or is reported, per `mode`. Implies `racc`. |
| **[Generative Hygiene](#generative-hygiene)** | `hyg` | on | [code](hooks/csop-gate-hyg.py) | Comment hygiene on agent-generated code. Implies `racc`. |
| **[IsolatedTree](#isolatedtree)** | `iso` | opt-in | [code](hooks/csop-gate-isowrite.py) | Risky/exploratory/experimental changes to a project's core must be prototyped in an isolated git worktree (an 'iso-tree') under the crash-safe, in-repo, gitignored `home` (default scratch/iso/), never /tmp. |
| **Scratch** | `scratch` | on | [code](hooks/csop-gate-scratch.py) | Discourages/denies destructive commands, directing agent to use scratch folder. |
| **Promotion** | `pro` | opt-in | [code](hooks/csop-gate-promotion.py) | Changes to core should be deliberate promotions of work proven in an iso-tree/scratch (small, tested, reviewable diffs), not ad-hoc edits. |
| **[Frozen Features](#frozen-features)** | `freeze` | opt-in | [code](hooks/csop-gate-pathblock.py) | Protects frozen paths and file regions from access. |
| **Test-Driven Development** | `tdd` | opt-in | [code](hooks/disciplines.py) | Tests-first workflow. |
| **Feature Spike** | `spike` | opt-in | [code](hooks/disciplines.py) | A time-boxed, throwaway exploratory spike to de-risk or learn. |
| **Performance** | `perf` | opt-in | [code](hooks/disciplines.py) | Measure-first performance discipline. |
| **Tactical Retreat** | `tactical` | opt-in | [code](hooks/disciplines.py) | When a change/experiment is going badly, cleanly retreat to a known-good state and rethink instead of accumulating hacks or churning flip/revert/flip. |
| **Stepwise** | `step` | opt-in | [code](hooks/disciplines.py) | Small-increment method. |
| **Consensus** | `consensus` | opt-in | [code](hooks/disciplines.py) | Corroboration / multi-perspective method. |
| **Groomer** | `groom` | opt-in | [code](hooks/disciplines.py) | Behavior-preserving style sweeps (conflicts with iso). |
| **[Technical Writer](#technical-writer)** | `techwrite` | opt-in | [code](hooks/csop-gate-techwrite.py) | Clear technical writing. |

The pattern with the more interesting stuff is generalizing a prompt-based role into something more like a legitimate *practice*.  (Do you prefer to trust a merely prompted "scientist" role, or one that's actually forced to step through the scientific method? 🤔)


-------------------------------------------

## Install

Projects opt in to CSOP using plain files wired through `${CLAUDE_PROJECT_DIR}`; no marketplace, no plugin install, no manifest. Just put a checkout somewhere in (or reachable from) the project, then run `make install` **from** CSOP, **inside** the project folder.

### Reqs 

**Requires Claude Code v2.1.196 or later.** The `/csop`, `/disc`, `/discipline`, `/stage`, `/promote`, `/demote`, and `/csop-disable` commands run `csop.py` via `${CLAUDE_PROJECT_DIR}`, which Claude Code substitutes in a command body only on v2.1.196+ (hooks get it on any version). On older CLIs the variable is left empty and the command fails with a "can't open file" error. `make install` (and `make init`) check `claude --version` and **refuse to proceed** below v2.1.196, writing nothing; upgrade the CLI, or bypass at your own risk with `SKIP_VERSION_CHECK=1`.

### Submodule

Recommended.  People hate submodules, but the approach means a plugin-version is pinned and upgrades are a `git` command.  **You probably don't want to just trust me on this,** so just fork this plugin repo to your own ownership.

Technically the submodule can use any directory, but the natural thing is to put the plugin itself inside the your upstream client-project's claude folder, then do the project-integration from there:

```bash
git submodule add \
  https://github.com/mattvonrocketstein/claude-SOP .claude/csop \
&& make -C .claude/csop install
```

This writes the project's `.claude/settings.json` (hooks pointing back at the submodule), and creates the `/csop`, `/disc`, `/discipline`, `/stage`, `/promote`, `/demote`, and `/csop-disable` commands. It never overwrites an existing `settings.json`; if one is present it prints a note showing what to merge. Then:

- add `.claude/csop-state/` to the project's `.gitignore` (runtime state),
- start a Claude Code session in the project and approve workspace trust once.

The default disciplines activate immediately; opt into the rest with `/csop enable <name>`. Turn one back off with `/csop-disable <name>`, or `/csop-disable all`.

Disabling is human-only. The agent can arm a discipline but never disarm one: an always-on rail, [`csop-gate-disarm.py`](hooks/csop-gate-disarm.py), blocks every route from a tool call to a smaller active set, including edits to csop's own state. A slash command reaches `disable` because its body runs a fixed command shape that the rail escalates to a permission prompt, and only a human can clear a prompt. Approve one only when you just typed the command yourself.


Upgrade later with `git submodule update --remote`; teammates run `git submodule update --init` after cloning.

### Without Submodule

Any checkout works the same way. Clone or copy the files anywhere and run the
same target:

```bash
git clone https://github.com/mattvonrocketstein/claude-SOP tools/csop
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

-------------------------------------------

## Discipline Details

### IsolatedTree

`iso` · opt-in · enable with `/csop enable iso`

Prototype risky, exploratory, or experimental changes to core in a **throwaway git
worktree**, proving them against tests there, then port only the clean diff
back, so a failed experiment never touches core.

**Lifecycle**

<ul>
  <li><strong>Create a FRESH tree per task</strong>: <code>git worktree add scratch/iso/&lt;name&gt; &lt;clean-base&gt;</code>. One task, one tree.</li>
  <li><strong>Iterate and test inside the tree</strong>: commit WIP there freely; the tree is disposable.</li>
  <li><strong>Rebase onto core for freshness</strong> before promoting (<code>git -C scratch/iso/&lt;name&gt; rebase &lt;core&gt;</code>), so the diff reconciles against current core, not a stale base.</li>
  <li><strong>Promote by EDITS/INSERTS</strong>: hand-apply the proven diff into core files; never a git merge.</li>
  <li><strong>Discard the tree</strong> once the diff has landed.</li>
</ul>

**Enforced restrictions**

<ul>
  <li><strong>Location</strong>: a tree MUST live under <code>scratch/iso/</code> (crash-safe, in-repo, gitignored), never <code>/tmp</code>; a <code>git worktree add</code> elsewhere is blocked.</li>
  <li><strong>No reuse</strong>: the first write into a tree this session did not create fresh is blocked; a leftover tree is stale or WIP (unknown state), so work must not begin there.</li>
  <li><strong>Session-owned</strong>: only the session that created a tree may write into it.</li>
  <li><strong>Promotion is edits, not merges</strong>: under Human Accountability a git merge/commit into core is denied (a &ldquo;quiet commit&rdquo;); reconcile by editing core, and a human commits.</li>
  <li><strong>Sandbox git</strong>: history ops confined to a tree (rebase, commit) are allowed; ops that escape it (<code>push</code>/<code>pull</code>, <code>gc</code>/<code>prune</code>/<code>filter-*</code>) stay denied.</li>
  <li><strong>Reads are never gated</strong>; lift a step deliberately by exporting <code>CSOP_ISO=off</code> in your session.</li>
</ul>

**Config** (`.claude/csop.json`, project-overridable)

<ul>
  <li><code>home</code>: where trees must live (default <code>scratch/iso/</code>).</li>
</ul>

### Frozen Features

`freeze` · opt-in · enable with `/csop enable freeze`

Protect stable or generated paths, and specific **regions inside a file**, from
edits. The discipline's `frozen` list is empty by default; a project fills it in
`.claude/csop.json`. Each entry is a bare path fragment, or a mapping for finer
control.

**What an entry can protect**

<ul>
  <li><strong>A whole file</strong>: a path fragment like <code>config/prod.yaml</code>.</li>
  <li><strong>A directory subtree</strong>: a fragment like <code>src/legacy/</code> (a &ldquo;section&rdquo; of the project).</li>
  <li><strong>A region inside a file</strong>: a mapping carrying <code>regex</code> and/or <code>prose</code> (below); the rest of the file stays editable.</li>
</ul>

**Whole-path modes**

<ul>
  <li><strong><code>no-write</code></strong> (default): the path may be READ but not modified; Edit/Write/MultiEdit are blocked.</li>
  <li><strong><code>no-touch</code></strong>: READS are blocked too (Read/Grep/Glob and Bash references), for a generated/build-artifact copy where reading the stale copy is itself a trap; the message redirects to the entry's <code>use</code> (the real source).</li>
  <li><strong><code>no-restructure</code></strong>: tool edits pass, since the subtree is meant to be edited in place, but a destructive shell verb (<code>rm</code>/<code>mv</code>/<code>cp</code>) naming the path is stopped. <code>no-write</code> stops such a verb too.</li>
</ul>

An entry may also carry <code>exempt</code> fragments (a worktree copy, say) that skip the shell check when they appear in the command or the invocation cwd. Path matching ignores a leading word character, so a fragment <code>.cmk/</code> is not found inside <code>foo.cmk/</code>.

**File regions**

<ul>
  <li><strong><code>regex</code>, a hard rule.</strong> A pattern bracketing the protected span (e.g. <code>&lt;!-- FROZEN --&gt;.*&lt;!-- END --&gt;</code>). A write whose edited text overlaps a match is BLOCKED; edits elsewhere in the file pass. <code>.</code> matches across lines.</li>
  <li><strong><code>prose</code>, a soft nudge.</strong> A natural-language description of the region (e.g. &ldquo;the generated client stubs&rdquo;). Prose can't be located precisely, so any write to the file emits a one-time reminder rather than a block.</li>
  <li>An entry may carry both: <code>regex</code> enforces, <code>prose</code> explains.</li>
</ul>

**Enforcement**

<ul>
  <li>Whole-path and <code>regex</code> hits use the discipline's <code>action</code> (default <code>block</code>; also <code>deny</code> / <code>ask</code> / <code>nudge</code>).</li>
  <li><code>prose</code> regions are always a nudge, never a hard block.</li>
  <li>Reads are never gated except under <code>no-touch</code>.</li>
  <li>Escape hatch: export <code>CSOP_FREEZE=off</code> in your session for a deliberate, authorized change.</li>
</ul>

**Config** (`.claude/csop.json`, project-overridable)

<ul>
  <li><code>frozen</code>: the list of entries (paths and/or mappings); empty by default.</li>
  <li><code>mode</code>: default mode for a bare-path entry (<code>no-write</code>).</li>
  <li><code>action</code>: enforcement strength for hard hits.</li>
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

### Human Accountability

`hacc` · default-on (opt out with `"default_enabled": false`)

Git is read-only for the agent. Commands that mutate history, branches, the working tree, or a remote (commit, checkout, reset, rebase, merge, push, rm, and the like) are denied at the permission layer, so a human runs core git. The agent still reads git freely and runs `git add`.

**Enforced restrictions**

<ul>
  <li><strong>Write subcommands denied.</strong> A git subcommand in <code>deny_list</code> is blocked; read-only git (<code>status</code>/<code>log</code>/<code>diff</code>/<code>show</code>) and <code>git add</code> pass.</li>
  <li><strong>Iso-tree carve-out.</strong> When <code>iso</code> is active, history ops confined to a tree (<code>git -C scratch/iso/&lt;name&gt; rebase</code>/<code>commit</code>) are allowed; ops that escape it (<code>push</code>/<code>pull</code>, <code>gc</code>/<code>prune</code>/<code>filter-*</code>) stay denied. Promotion into core is by edits, never a merge or commit.</li>
  <li><strong>Escape hatch:</strong> export <code>CSOP_HACC=off</code> for a deliberate, authorized git write.</li>
</ul>

**Config** (`.claude/csop.json`, project-overridable)

<ul>
  <li><code>deny_list</code>: the git subcommands the agent may not run.</li>
  <li><code>default_enabled</code>: on by default; set false to opt this project out.</li>
</ul>

### Robot Accountability

`racc` · opt-in, and co-activated by [Generative Hygiene](#generative-hygiene) · enable with `/csop enable racc`

The agent must change files visibly through the Edit or Write tool, which shows a diff, not through in-place shell mutations. It is the robot counterpart to Human Accountability: no sneaky edits by shell.

Because `hyg` is default-on, `racc` is normally active too. Hygiene and technical writing inspect Edit and Write payloads only, so an in-place shell write would otherwise be an unchecked path around them.

**Enforced restrictions**

<ul>
  <li><strong>In-place shell writes denied.</strong> A Bash command that rewrites a file in place (<code>sed -i</code>, <code>perl -i</code>, in-place <code>awk</code>, <code>tee</code>, <code>dd</code>, <code>truncate</code>, or a <code>&gt;</code>/<code>&gt;&gt;</code> redirect or heredoc to a file) is denied; make the change through the Edit tool.</li>
  <li><strong>Other invisible writes denied.</strong> A patch applied by <code>patch</code> or by git, a line editor (<code>ed</code>, <code>ex</code>), <code>install</code>, and an inline interpreter script (<code>python -c</code>, <code>node -e</code>, a <code>-</code> heredoc) that opens a file for writing. This is what keeps the write-side gates honest: hygiene and technical writing only see Edit and Write, so a shell write would otherwise slip past them.</li>
  <li><strong>Read-only shell passes</strong> (a redirect to <code>/dev/null</code> or a file-descriptor dup is fine).</li>
  <li><strong>Escape hatch:</strong> export <code>CSOP_RACC=off</code>.</li>
</ul>

**Config** (`.claude/csop.json`, project-overridable)

<ul>
  <li><code>action</code>: enforcement strength (default <code>deny</code>).</li>
  <li><code>default_enabled</code>: off by default.</li>
</ul>

### Memory Accountability

`mem` · opt-in · implies [`racc`](#robot-accountability) · enable with `/csop enable mem`

Memory formation is a human decision, not a side effect. A memory file outranks instructions in every later session, so a wrong one, recorded from an error, a flaky result, or a single-run observation, is expensive and quiet. The discipline governs writes to the memory paths and makes each one either the human's call or, at minimum, audible.

`racc` comes along because the gate sees Edit and Write only; without it a shell redirect would write a memory unobserved.

**Modes** (`mode`, default `approval`)

<ul>
  <li><code>approval</code>: the write asks the human first, quoting the proposed memory text. It rests on <code>ask</code>, which overrides every permission mode, so it is the setting that holds everywhere.</li>
  <li><code>amnesiac</code>: the write is denied outright. It rests on <code>deny</code>, which the permission layer ignores under <code>bypassPermissions</code>; if a write lands anyway, the reporter raises it as an alarm.</li>
  <li><code>visible</code>: the write is allowed and named in the end-of-turn modeline. A memory can still form, but never in silence.</li>
</ul>

**Enforced restrictions**

<ul>
  <li><strong>Memory paths only.</strong> A write is governed when its target matches <code>paths</code>: <code>MEMORY.md</code>, project and user <code>CLAUDE.md</code>, and any <code>memory/</code> directory. Every other write passes untouched.</li>
  <li><strong>Retraction passes.</strong> An edit that only removes memory text is allowed under <code>allow_retraction</code>, which keeps correcting a bad memory cheap.</li>
  <li><strong>Landed writes are reported.</strong> A PostToolUse reporter speaks under <code>visible</code> and <code>amnesiac</code>, quoting up to <code>excerpt_chars</code> of what was recorded.</li>
  <li><strong>Escape hatch:</strong> export <code>CSOP_MEM=off</code>.</li>
</ul>

**Config** (`.claude/csop.json`, project-overridable)

<ul>
  <li><code>mode</code>: <code>approval</code> (default), <code>amnesiac</code>, or <code>visible</code>.</li>
  <li><code>paths</code>: the governed memory paths; project entries are appended to the defaults.</li>
  <li><code>allow_retraction</code>: let removal-only edits through (default true).</li>
  <li><code>excerpt_chars</code>: cap on quoted memory text in a prompt or modeline notice (default 120).</li>
  <li><code>default_enabled</code>: off by default.</li>
</ul>

### Generative Hygiene

`hyg` · default-on (opt out with `"default_enabled": false`) · implies [`racc`](#robot-accountability)

Comment hygiene on agent-generated code. It rejects the tells of a model narrating to itself in the source: over-long comment blocks, code syntax quoted in comments, and shouted words. Reasoning belongs in a notes or spike doc under `notes_dir`, not in the code.

**Enforced restrictions** (added text only, so grandfathered comments are left alone)

<ul>
  <li><strong>Comment budgets</strong>, two of them, split by marker shape.
    <ul>
      <li>A comment attached to code (<code>#</code>, <code>//</code>, <code>--</code>, <code>;;</code>) is chain-of-thought territory: <code>max_comment_lines</code>, default 1.</li>
      <li>Documentation &mdash; a <code>doc_prefixes</code> line or a <code>doc_regions</code> region &mdash; gets <code>doc_max_comment_lines</code>, default 6, and skips the syntax rule since documentation legitimately shows code.</li>
      <li>Neither budget is unlimited. A docstring long enough to be a novel is the same defect as a comment block long enough to be one.</li>
      <li>Marker shape is the whole test. Where a block sits relative to what it documents is language-specific, so the gate does not guess; encode the distinction in <code>doc_prefixes</code>/<code>doc_regions</code>.</li>
    </ul>
  </li>
  <li><strong>Counting rules.</strong>
    <ul>
      <li>Blank lines and bare delimiter lines carry no prose and cost nothing.</li>
      <li>A section banner ruled off with dashes is structure, so it separates runs rather than joining one.</li>
      <li>A block is judged at its <em>resulting</em> size, not the size of the diff, so it cannot be grown past budget by repeated small appends.</li>
      <li>A block already over budget can still be edited in place or shrunk &mdash; only growth is refused, and the message names the transition (<code>grew a documentation block from 11 to 12 lines</code>) and quotes the added line.</li>
    </ul>
  </li>
  <li><strong>What counts as a comment is decided by file type.</strong> The <code>comment_markers</code> table maps an extension to that language's line-comment markers: <code>#</code> for Python and shell, <code>//</code> for C-likes, <code>--</code> for SQL and Lua, <code>;</code> for Lisps. A language with no line comment maps to an empty list, so a CSS <code>#header</code> is a selector rather than a comment, and a <code>#</code> line in a <code>.js</code> file is not a comment either. Unlisted types fall back to <code>unknown_markers</code>.</li>
  <li><strong>No code in comments.</strong> A comment matching a <code>syntax_rules</code> regex (a call like <code>foo(</code>, a shell/make sigil, an operator, braces) is rejected; describe it in prose.</li>
  <li><strong>No shouting.</strong> An all-caps word used for emphasis is rejected; a real global or env-var keeps its underscores and passes, and acronyms live in <code>shout_ok</code>. Unlike the rules above this one is <em>not</em> waived for documentation: it covers every comment and documentation line alike, because prose a human reads does not shout.</li>
  <li><strong>Scope.</strong>
    <ul>
      <li>Out: files whose extension is in <code>prose_exts</code> (<code>md</code>, <code>markdown</code>, <code>mdx</code>, <code>rst</code>, <code>txt</code>, <code>adoc</code>, <code>org</code>), anything under a <code>prose_dirs</code> subtree (<code>docs/</code>), and the <code>notes_dir</code>.</li>
      <li>In: an iso tree under the notes_dir, which holds code bound for core, so the promoted diff matches what core accepts.</li>
      <li>Markdown belongs to <a href="#technical-writer">Technical Writer</a> instead; the two gates partition the tree rather than overlap.</li>
    </ul>
  </li>
  <li><strong>Shell writes closed off.</strong> Enabling <code>hyg</code> also activates <a href="#robot-accountability">Robot Accountability</a>, since this gate sees only Edit and Write; without it, a <code>sed -i</code> or a heredoc would write comments the gate never reads.</li>
  <li><strong>Escape hatch:</strong> export <code>CSOP_HYG=off</code>.</li>
</ul>

**Awareness** (what the model is told, apart from a rejection)

<ul>
  <li><strong>Pre-turn <code>nudge</code></strong>, injected at the top of every turn by the UserPromptSubmit hook while hyg is active: the rule in one paragraph, so the model writes to it rather than discovering it by being blocked.</li>
  <li><strong>Post-turn <code>reminder</code></strong>: hyg does not define one. Reminders are for follow-up tasks a turn leaves behind, and hygiene has none &mdash; a violation is refused outright rather than deferred. Only <code>iso</code> and <code>spike</code> carry reminders today.</li>
  <li><strong>On rejection</strong>, the message lists each finding with the offending line, then a tail assembled from only the rules that actually fired.</li>
</ul>

**Config** (project-overridable; see <a href="#configuration-layering">Configuration layering</a>)

<ul>
  <li><code>max_comment_lines</code> / <code>doc_max_comment_lines</code>: the two budgets (default 1 and 6).</li>
  <li><code>doc_prefixes</code> / <code>doc_regions</code>: what counts as documentation rather than a code comment.</li>
  <li><code>syntax_rules</code>: the code-in-comment regexes. <code>shout_ok</code>: the all-caps words that pass (appends).</li>
  <li><code>prose_exts</code> / <code>prose_dirs</code>: extensions and subtrees treated as prose and skipped (both append).</li>
  <li><code>comment_markers</code> / <code>unknown_markers</code>: the per-file-type line-comment markers, and the fallback for a type not in the table.</li>
  <li><code>notes_dir</code>: where reasoning should go instead (default <code>scratch/</code>).</li>
  <li><code>action</code>: enforcement strength (default <code>block</code>).</li>
</ul>

### Technical Writer

`techwrite` · opt-in · enable with `/csop enable techwrite` (implies `hyg`, and `racc` through it)

Clear technical writing, plus a lint against generated-prose tells and code leaking into docs. The awareness half nudges the usual moves: lead with the point, stay concise, prefer active voice, structure with headings and lists, show with an example. The enforcement half checks added text.

**Enforced restrictions**

<ul>
  <li><strong>Banned substrings, any file.</strong> A substring in <code>banned</code> (default: the em-dash, plus generated-prose cliches) in an added line is rejected; these read as a machine, not a human.</li>
  <li><strong>Prose rules, scoped docs.</strong> In files matching <code>prose_globs</code>, each <code>prose_rules</code> regex flags code leaking into prose (a shell/make expansion, a bare <code>self.</code> anchor). Fenced blocks, backtick spans, Jinja, HTML code regions, and tables are masked first, so a signal inside a real code region is exempt.</li>
  <li><strong>Span strictness and opt-outs.</strong> A rule with <code>in_spans</code> also checks inside backticks; a line carrying the <code>token</code> (default <code>docs-code-ok</code>) opts out; <code>exempt</code> basenames are skipped entirely.</li>
  <li><strong>Escape hatch:</strong> export <code>CSOP_TECHWRITE=off</code>.</li>
</ul>

**Config** (`.claude/csop.json`, project-overridable)

<ul>
  <li><code>banned</code>: substrings rejected in any added text, matched case-insensitively (default the em-dash, a stock cliche, and a handful of model tics).</li>
  <li><code>prose_globs</code>: which files the prose rules apply to.</li>
  <li><code>prose_rules</code>: <code>{pattern, message, in_spans}</code> regexes for code-in-prose; empty by default.</li>
  <li><code>discouraged</code>: prose-only words that warn without ever blocking (default <code>gate</code>, <code>leverage</code>, <code>substrate</code>).</li>
  <li><code>token</code> / <code>exempt</code>: the per-line opt-out marker and the skipped basenames.</li>
  <li><code>action</code>: enforcement strength (default <code>deny</code>).</li>
</ul>

-------------------------------------------

## Configuration layering

A discipline's identity lives in code; its behavior is tunable in three layers,
each overriding the one before it.

<ol>
  <li><strong>Code default</strong> &mdash; the class attribute in <code>hooks/disciplines.py</code>.</li>
  <li><strong>Project</strong> &mdash; <code>.claude/csop.json</code>, keyed by codename.</li>
  <li><strong>Current stage</strong> &mdash; the <code>stages</code> block's <code>disciplines</code> object for whichever stage is current, so a rule can be strict in one phase and relaxed in another.</li>
</ol>

Only the properties a discipline lists in `overridable` can be set; a name or
description never can. A property also listed in `append` **adds** to the value
below it rather than replacing it (`shout_ok`, `prose_exts`, `prose_dirs`,
`nudge`, `reminder`), so a project extends the built-in list instead of erasing
it. Everything else replaces.

```jsonc
{
  "hyg": { "doc_max_comment_lines": 12, "prose_exts": ["vue"] },
  "stages": {
    "draft":  { "disciplines": { "hyg": { "action": "nudge" } } },
    "polish": { "from": ["draft"], "disciplines": { "hyg": { "action": "block" } } }
  }
}
```

A stage becomes current via `/csop stage <name>` (or `/promote`), and the stage
layer applies to every gate that reads its discipline through `get()`.

-------------------------------------------

## Abstractions 

### Modeline

A plugin cannot drive the built-in status line, so `csop-modeline.py` (a `Stop` hook)
falls back to printing a footer at the end of each turn: a `⬥ CSOP ::` head
carrying a dimmed pointer to `/csop help`, then one line per body item, each hung
off the head with a `↳` so the block reads as one unit under the host's own
preamble. Reminders and one-time notices hang the same way.

```
⬥ CSOP :: Use /csop help for details.
↳ Disciplines: hyg, iso, pro
↳ Stages: spike, [core], ship
↳ IsolatedTree: ...follow-up reminder...
```

The two components read differently, so they are labelled differently.
`Disciplines` lists only what is **active**: everything shown is on. `Stages`
(shown when `pro` is active) lists every stage the project **defines**, with the
current one in `[brackets]`, and `(none current)` appended when none is set.
Markers, not styling, carry that meaning: the desktop app renders neither ANSI
nor markdown, so anything style-only is invisible there.

Silent when every component is empty. It never blocks (exits 0, guards on `stop_hook_active`), so
it can't cause a continuation loop.

**Display channel.** Raw `Stop`-hook stdout is NOT shown to the user (confirmed);
the modeline emits the documented user-visible **`systemMessage`** JSON field
(exit 0), which Claude Code renders as an end-of-turn notice.

### Status line (opt-in, CLI only)

`csop-statusline.py` renders the same disciplines/stage summary as the modeline,
but through Claude Code's `statusLine` setting instead of a `Stop` hook: real ANSI
color and real `COLUMNS`/`LINES` (confirmed live), versus the modeline's plain,
occasionally-wrapping `systemMessage` text. Confirmed CLI-only -- a genuine cold
start of the desktop app showed no statusLine output at all, so this is additive,
not a replacement; `csop-modeline.py` stays wired for every surface.

It is deliberately **not** wired by `make init`/`make install`: `statusLine` is a
single-slot setting, and writing it into the shared, committed `.claude/settings.json`
would silently override any teammate's own status line the moment they pull. Add
it yourself to `.claude/settings.local.json` in the project instead -- Claude Code
keeps that file out of git automatically, and it takes precedence over the shared
`.claude/settings.json` and your `~/.claude/settings.json`, so it is a pure,
per-person, per-project opt-in:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 \"${CLAUDE_PROJECT_DIR}/hooks/csop-statusline.py\""
  }
}
```

## Misc Notes 

### Compatibility

Needs Claude Code **v2.1.196+**: slash commands resolve `csop.py` through `${CLAUDE_PROJECT_DIR}`, which a command body substitutes only on 2.1.196+ (`make install` enforces this).
Hooks and the `python3` (stdlib-only) machinery run on any version.

### Self-protection

CSOP's own hook code under `hooks/` is read-only in a consumer project: an always-on gate denies Edit/Write of the vendored plugin copy, so fixes go upstream in the `claude-SOP` repo and reach the client by a submodule update. It is inert in the plugin's own repo. Escape hatch: `CSOP_SELFPROTECT=off`.

### Runtime / dependencies

Hooks are **stdlib-only** by policy. A plugin has no runtime-dependency
mechanism: a hook is a command the harness runs through the host shell, using
whatever `python3` is on PATH: **no venv, no container, no install**. Because
these scripts import only the Python standard library, the only prerequisite is
a `python3` interpreter (near-universal, already assumed by Claude Code), so the
plugin works on a fresh machine with zero setup.

- Do NOT add third-party (`pip`) dependencies to hooks.
- Do NOT shell out to a container per gate, since PreToolUse fires on ~every tool
  call, so container startup cost is prohibitive.
- If a future discipline truly needs a heavy dependency: vendor a pure-Python
  package onto `sys.path`, or bootstrap a venv in `${CLAUDE_PLUGIN_DATA}` from a
  SessionStart hook. Never a container-per-call.
- No `python3` on PATH → hooks fail-open (tool proceeds, discipline off).
