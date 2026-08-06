#!/usr/bin/env python3
"""CSOP discipline DEFINITIONS.

A discipline is a SINGLETON class. Its identity (codename / name / description)
and its default properties (default_enabled + params like `dir` / `deny_list` /
`reminder`) live HERE, in code -- NOT in config. A project's `.claude/csop.json`
may only OVERRIDE the properties a discipline lists in `OVERRIDABLE`, which
SUPERSEDE the class defaults. You never set a name/description in config.

Merge modes: an OVERRIDABLE property normally REPLACES the code default; a
property also listed in `APPEND` is APPENDED to the code default instead (used
for `reminder`, so a project's reminder adds to -- never erases -- the built-in).

Gates / hooks read a discipline's effective property via `<Discipline>.get(key)`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402  (substrate: project_config loader)


class _Ref:
    """A read-through handle to a sibling discipline for reminder templates:
    `{codename.var}` resolves to that sibling's OWN effective value (its default
    plus its own appends/config), not the referrer's -- via getattr on get()."""
    def __init__(self, d):
        self._d = d

    def __getattr__(self, name):
        return self._d.get(name)


class Discipline:
    codename = ""
    name = ""
    description = ""
    default_enabled = False
    requires = ()                            # codenames this discipline co-activates (implies on)
    reminder = ""                            # top-of-turn awareness text (while active)
    OVERRIDABLE = ("default_enabled", "reminder")   # props a project may override
    APPEND = ("reminder",)                   # OVERRIDABLE props whose override is
                                             # APPENDED to the code default, not replaced

    @classmethod
    def get(cls, key):
        """Effective value: the class (code) default, with the project override
        from `.claude/csop.json[codename]` applied if `key` is OVERRIDABLE and
        present. APPEND props append to the code default; others replace it."""
        default = getattr(cls, key)
        if key in cls.OVERRIDABLE:
            over = csop.project_config().get(cls.codename, {})
            if key in over:
                if key in cls.APPEND:
                    return cls._append(default, over[key])
                return over[key]
        return default

    @staticmethod
    def _append(default, extra):
        if isinstance(default, str) and isinstance(extra, str):
            return (default + "\n" + extra) if default else extra
        if isinstance(default, list) and isinstance(extra, list):
            return default + extra
        return extra

    @classmethod
    def _params(cls):
        """This discipline's effective params (OVERRIDABLE minus `reminder`) --
        the substitution context for templated text."""
        return {k: cls.get(k) for k in cls.OVERRIDABLE if k != "reminder"}

    @classmethod
    def render(cls, key):
        """`get(key)`, then str.format it JIT against the effective config: this
        discipline's own params at top level, plus every discipline as a sibling
        handle keyed by codename, so a reminder can reference another discipline
        directly, e.g. `{hacc.deny_list}` or `{scratch.scratch_dir}`. Fail-open:
        an unknown/broken placeholder leaves the text literal so a config typo can
        never brick a hook."""
        text = cls.get(key)
        if not isinstance(text, str):
            return text
        ctx = dict(cls._params())
        for d in DISCIPLINES:
            ctx[d.codename] = _Ref(d)
        try:
            return text.format(**ctx)
        except Exception:
            return text


class IsoTree(Discipline):
    codename = "iso"
    name = "IsolatedTree"
    default_enabled = False
    dir = "scratch/iso/"
    reminder = ("IsolatedTree active: prototype risky/exploratory/experimental "
                "changes to core in an ISO-TREE under the iso dir `{dir}`, never "
                "/tmp; iterate + test there, then port only the proven diff back "
                "to core -- don't edit core in place for exploratory work. Use a "
                "FRESH tree per task -- NEVER reuse an existing tree (its state is "
                "unknown: stale or WIP); begin a new task with `git worktree add "
                "{dir}<new> <clean-base>`.")
    OVERRIDABLE = ("default_enabled", "dir", "reminder")
    description = ("Risky/exploratory/experimental changes to a project's core "
                  "must be prototyped in an isolated git worktree (an 'iso-tree') "
                  "under the crash-safe, in-repo, gitignored `dir` (default "
                  "scratch/iso/), never /tmp. Prove against tests there, then "
                  "port the diff back to core. Enforced: worktree-add must target "
                  "the iso dir, and the first write into a tree not created fresh "
                  "by this session is blocked (no reusing stale/WIP trees).")


class HumanAccountability(Discipline):
    codename = "hacc"
    name = "Human Accountability"
    default_enabled = True
    deny_list = ["commit", "stash", "checkout", "switch", "reset", "rebase",
                 "merge", "push", "pull", "revert", "restore", "clean",
                 "cherry-pick", "am", "rm", "mv", "apply", "gc", "prune",
                 "filter-branch", "filter-repo"]
    reminder = ("Human Accountability active: git is READ-ONLY for you -- don't "
                "commit/stash/checkout/push/reset/rm/etc; ask the human to run "
                "git writes. EXCEPTION when iso is active: git history ops "
                "CONFINED to an iso tree are allowed (`git -C {iso.dir}<name> "
                "rebase <core>` for freshness). NEVER merge/commit into core -- "
                "promote a tree by EDITS/INSERTS. Git reads and `git add` are fine.")
    OVERRIDABLE = ("default_enabled", "deny_list", "reminder")
    description = ("Git is read-only for the agent: the git subcommands in "
                  "`deny_list` are DENIED. Git reads and `git add` (staging) "
                  "pass through. A human must run git writes directly (or lift "
                  "via CSOP_HACC=off); the agent cannot alter history / branches "
                  "/ working-tree / remote. When `iso` is active, git history ops "
                  "CONFINED to an iso tree (rebase-for-freshness) are exempt -- "
                  "they cannot commit into core; promotion into core is by EDITS, "
                  "never a git merge.")


class Scratch(Discipline):
    codename = "scratch"
    name = "Scratch"
    default_enabled = True
    scratch_dir = "scratch/"          # MOVE content here instead of destroying it
    # Bash commands matching ANY of these regexes are DENIED (irreversibly
    # destructive). Project-overridable via `deny_patterns` (replaces the list).
    deny_patterns = [
        r"\brm\b[^;&|]*\s-\S*r\S*f",
        r"\brm\b[^;&|]*\s-\S*f\S*r",
        r"\brm\b[^;&|]*(?:\s-r\b|\s--recursive\b)[^;&|]*(?:\s-f\b|\s--force\b)",
        r"\brm\b[^;&|]*(?:\s-f\b|\s--force\b)[^;&|]*(?:\s-r\b|\s--recursive\b)",
        r"\bgit\b[^;&|]*\breset\b[^;&|]*--hard\b",
        r"\bgit\b[^;&|]*\bclean\b[^;&|]*\s-\S*f",
        r"\bgit\b[^;&|]*\bpush\b[^;&|]*(?:--force\b|\s-f\b)",
        r"\bgit\b[^;&|]*\bcheckout\b[^;&|]*(?:--\s+)?\.(?:\s|$)",
        r"\bgit\b[^;&|]*\bbranch\b[^;&|]*\s-D\b",
        r"\bgit\b[^;&|]*\bstash\b[^;&|]*\b(?:clear|drop)\b",
        r"\bgit\b[^;&|]*\breflog\b[^;&|]*\b(?:expire|delete)\b",
        r"\bgit\b[^;&|]*\bupdate-ref\b[^;&|]*\s-d\b",
        r"\bgit\b[^;&|]*\bfilter-(?:branch|repo)\b",
        r"\bshred\b", r"\bmkfs\b", r"\bdd\b[^;&|]*\bof=",
    ]
    reminder = ("Scratch active: destructive operations are discouraged/disabled "
                "-- take content out of circulation by moving it to `{scratch_dir}` "
                "instead of deleting it.")
    OVERRIDABLE = ("default_enabled", "deny_patterns", "scratch_dir", "reminder")
    description = ("Discourages/denies irreversibly destructive commands: "
                   "dangerous recursive+force file removal and the 'nuclear "
                   "options' in git (reset --hard, clean -f, force push, "
                   "checkout ., branch -D, stash drop/clear, reflog expire, "
                   "filter-branch/repo), plus shred/mkfs/dd. The safe alternative "
                   "is to MOVE content out of circulation into `scratch_dir`. "
                   "Match rules + scratch_dir are project-overridable.")


# NOTE: `action` below is a DRAFT config slot = the intended enforce strength
# (nudge | ask | deny | block). The generic gate-side reader for it is not built
# yet; until then these disciplines are AWARENESS-only (their `reminder` is
# injected top-of-turn by reminder.py when active). Wiring gates that consult
# `action` + each discipline's matcher param is the follow-up.

class Promotion(Discipline):
    codename = "pro"
    name = "Promotion"
    default_enabled = False
    core = ["src/**", "lib/**"]       # path globs treated as CORE (a project sets these)
    action = "nudge"
    reminder = ("Promotion active: changes to core should arrive as deliberate "
                "PROMOTIONS of work already proven in an iso-tree/scratch -- "
                "small, reviewable, test-passing diffs -- not ad-hoc in-place "
                "edits. Prototype first, then promote.")
    OVERRIDABLE = ("default_enabled", "core", "action", "reminder")
    description = ("Changes to CORE should be deliberate promotions of work "
                   "proven in an iso-tree/scratch (small, tested, reviewable "
                   "diffs), not ad-hoc edits. Pairs with IsolatedTree. Draft "
                   "gate: nudge/ask on direct edits to `core` paths.")


class GenerativeHygiene(Discipline):
    codename = "hyg"
    name = "Generative Hygiene"
    default_enabled = True
    max_comment_lines = 1             # >this ADDED comment lines in a run -> reject
    notes_dir = "scratch/"            # externalize chain-of-thought here, not in code
    # LANGUAGE-AGNOSTIC detection of CODE SYNTAX inside a comment, as a tunable
    # regex list (heuristic, expected to evolve). The signal is the shape/amount
    # of syntax, tuned to spare prose: a paren with a space before it `( aside )`
    # is fine; a call `foo(` (no space) is not.
    syntax_rules = [
        r"[)\]\w]\(",                 # call: token immediately before '(' (no space)
        r"\$\{|\$\(|\$\w",            # shell/make sigils
        r"=>|->|::|==|!=|&&|\|\|",    # code operators
        r"[{}]",                      # braces
    ]
    action = "block"
    reminder = ("Generative Hygiene active: do NOT externalize chain-of-thought "
                "into code comments -- at most one comment line per block, and no "
                "code syntax quoted in comments. Keep running notes / reasoning in "
                "a dedicated notes or spike doc under `{notes_dir}`; delete cruft, "
                "don't comment it out.")
    OVERRIDABLE = ("default_enabled", "max_comment_lines", "notes_dir",
                   "syntax_rules", "action", "reminder")
    description = ("Comment hygiene on agent-generated code: rejects adding more "
                   "than `max_comment_lines` comment lines in a block, or code "
                   "SYNTAX (per the `syntax_rules` regex list) inside a comment -- "
                   "pushing chain-of-thought out of code and into a notes/spike "
                   "doc under `notes_dir`. Prose/notes files are out of scope. "
                   "Language-agnostic; rules are a tunable list to experiment with.")


class FrozenFeatures(Discipline):
    codename = "freeze"
    name = "Frozen Features"
    default_enabled = False
    frozen = []                       # entries: a path fragment, or a mapping (see below)
    mode = "no-write"                 # default protection applied to a bare-path entry
    action = "block"
    reminder = ("Frozen Features active: the frozen paths are OFF-LIMITS. A "
                "no-write path must not be modified (reads are fine); a no-touch "
                "path must not even be read -- it is a generated/build-artifact "
                "copy, so reading the stale copy is itself a trap; use the source "
                "instead. Some entries protect only a REGION of a file (marker "
                "regex, or a described section) -- leave that region unchanged. "
                "If a change is truly needed, propose it for a human.")
    OVERRIDABLE = ("default_enabled", "frozen", "mode", "action", "reminder")
    description = ("Protects frozen paths and file REGIONS from access. Each "
                   "`frozen` entry is a path fragment (a file or a directory "
                   "subtree), or a mapping {path, mode, why, use, regex, prose}. "
                   "Whole-path modes: no-write (default) blocks modification while "
                   "reads pass; no-touch also blocks reads/Bash refs of a generated "
                   "copy. File regions: `regex` markers HARD-gate the matched span "
                   "of a file; `prose` describes a region as a soft NUDGE. "
                   "Enforcement = `action`; escape hatch CSOP_FREEZE=off. Gate: "
                   "pathblock over `frozen`.")


class TestDrivenDevelopment(Discipline):
    codename = "tdd"
    name = "Test-Driven Development"
    default_enabled = False
    test_globs = ["**/test_*.py", "**/*_test.*", "**/*.test.*", "tests/**", "spec/**"]
    src_globs = ["src/**", "lib/**"]
    test_command = "make test"
    action = "nudge"
    reminder = ("Test-Driven Development active: write a FAILING test first, then "
                "implement to green; don't change implementation without a "
                "matching test; run `{test_command}` after each change.")
    OVERRIDABLE = ("default_enabled", "test_globs", "src_globs", "test_command",
                   "action", "reminder")
    description = ("Tests-first workflow: a failing test precedes implementation; "
                   "implementation (`src_globs`) shouldn't change without a "
                   "matching test (`test_globs`); run `test_command` after "
                   "changes. Draft gate: nudge on src edits lacking a recent test "
                   "edit.")


class FeatureSpike(Discipline):
    codename = "spike"
    name = "Feature Spike"
    default_enabled = False
    spike_dir = Scratch.scratch_dir + "spike/"   # derived from the sibling's dir directly
    requires = ("hyg", "scratch")     # co-activate hygiene + the destructive-op guard
    action = "nudge"
    reminder = ("Feature Spike active: this is a time-boxed, THROWAWAY "
                "exploration to de-risk/learn -- keep it in `{spike_dir}`, a spike "
                "subdir of Scratch's `{scratch.scratch_dir}`; don't polish or "
                "productionize, and expect to discard and rewrite afterward.")
    OVERRIDABLE = ("default_enabled", "spike_dir", "action", "reminder")
    description = ("A time-boxed, throwaway exploratory spike to de-risk or learn "
                   "-- kept in `spike_dir` (derived from Scratch's `scratch_dir`), "
                   "not polished/productionized, expected to be discarded. Requires "
                   "Generative Hygiene + Scratch. Complements IsolatedTree "
                   "(isolation) by governing INVESTMENT. Draft: reminder-led.")


class Performance(Discipline):
    codename = "perf"
    name = "Performance"
    default_enabled = False
    benchmark_command = ""            # how to measure (project sets)
    action = "nudge"
    reminder = ("Performance active: MEASURE before optimizing (don't guess) -- "
                "profile hot paths, watch for N+1 / quadratic / repeated work and "
                "avoidable allocations, keep within budgets, and don't regress. "
                "Optimize only what a measurement shows is hot.")
    OVERRIDABLE = ("default_enabled", "benchmark_command", "action", "reminder")
    description = ("Measure-first performance discipline: profile before "
                   "optimizing, avoid premature optimization, watch for "
                   "quadratic/N+1 patterns, guard against regressions via "
                   "`benchmark_command`. Draft: reminder-led.")


class TacticalRetreat(Discipline):
    codename = "tactical"
    name = "Tactical Retreat"
    default_enabled = False
    action = "nudge"
    reminder = ("Tactical Retreat active: when an approach stops working, RETREAT "
                "cleanly -- revert to the last known-good state and rethink "
                "instead of piling fixes on a failing direction. Recognize the "
                "dead end early; avoid flip/revert/flip churn.")
    OVERRIDABLE = ("default_enabled", "action", "reminder")
    description = ("When a change/experiment is going badly, cleanly retreat to a "
                   "known-good state and rethink instead of accumulating hacks or "
                   "churning flip/revert/flip. Draft: reminder-led (a nudge after "
                   "repeated failed retries).")


class Dreamer(Discipline):
    codename = "dream"
    name = "Dreamer"
    default_enabled = False
    dir = Scratch.scratch_dir         # writes are confined here while active
    action = "deny"
    reminder = ("Dreamer active: diverge, don't converge -- brainstorm freely, "
                "generate many options, defer judgment. Capture ideas as notes in "
                "`{dir}`; structured writes OUTSIDE `{dir}` are DENIED -- think "
                "big / blue-sky, don't build yet.")
    OVERRIDABLE = ("default_enabled", "dir", "action", "reminder")
    description = ("Ideation / divergent-thinking mode: generate options freely, "
                   "defer judgment and implementation, don't prematurely converge "
                   "or start building. Enforced: structured writes are confined to "
                   "`dir` (default the scratch area); writes elsewhere are denied. "
                   "The 'diverge' counterpart to the execution disciplines.")


class Scientist(Discipline):
    codename = "science"
    name = "Scientist"
    default_enabled = False
    action = "nudge"
    reminder = ("Scientist active: form a HYPOTHESIS before changing anything, "
                "then test it -- change one variable at a time, predict the "
                "outcome, run the experiment, and let evidence (not assumption) "
                "decide. Reproduce before you conclude; record what you tried.")
    OVERRIDABLE = ("default_enabled", "action", "reminder")
    description = ("Empirical / hypothesis-driven method: state a hypothesis, "
                   "change one variable at a time, predict + measure, let evidence "
                   "decide, reproduce before concluding. Guards against "
                   "assumption-driven debugging. Draft: reminder-led.")


class Stepwise(Discipline):
    codename = "step"
    name = "Stepwise"
    default_enabled = False
    action = "nudge"
    reminder = ("Stepwise active: work in SMALL, verifiable increments -- one "
                "change at a time, check it (build/test/run) before the next, and "
                "keep each step reversible. No big-bang edits; land a working step "
                "before starting the next.")
    OVERRIDABLE = ("default_enabled", "action", "reminder")
    description = ("Small-increment method: make one change at a time, verify "
                   "before proceeding, keep each step reversible; no large "
                   "multi-concern edits. Complements TDD/Scientist. Draft: "
                   "reminder-led (a nudge on large/multi-file edits).")


class Consensus(Discipline):
    codename = "consensus"
    name = "Consensus"
    default_enabled = False
    action = "nudge"
    reminder = ("Consensus active: don't rely on a single take -- corroborate "
                "before acting. Cross-check a claim against more than one source / "
                "angle, seek a second opinion on consequential decisions, and "
                "surface disagreement rather than papering over it.")
    OVERRIDABLE = ("default_enabled", "action", "reminder")
    description = ("Corroboration / multi-perspective method: cross-check claims "
                   "against more than one source or angle, seek a second opinion "
                   "on consequential decisions, and surface disagreement instead "
                   "of settling on the first plausible answer. Draft: "
                   "reminder-led.")


class Groomer(Discipline):
    codename = "groom"
    name = "Groomer"
    default_enabled = False
    action = "nudge"
    reminder = ("Groomer active: leave things tidier than you found them -- as "
                "you pass through code/docs, fix small rough edges (naming, dead "
                "cruft, stale comments, TODOs) in scope, but don't sprawl into "
                "unrelated refactors. Boy-scout, not bulldozer.")
    OVERRIDABLE = ("default_enabled", "action", "reminder")
    description = ("Incremental tidying / boy-scout-rule: opportunistically groom "
                   "small rough edges (naming, dead cruft, stale comments) in the "
                   "area you're already touching, without sprawling into unrelated "
                   "refactors. Complements Generative Hygiene (clean NEW output) "
                   "by tending EXISTING code. Draft: reminder-led.")


class Toolsmith(Discipline):
    codename = "smith"
    name = "Toolsmith"
    default_enabled = False
    action = "nudge"
    reminder = ("Toolsmith active: when a task is repetitive or error-prone, "
                "invest in the TOOL -- write a script/target/helper instead of "
                "doing it by hand again, and prefer improving shared tooling over "
                "one-off workarounds. Sharpen the axe, but don't gold-plate.")
    OVERRIDABLE = ("default_enabled", "action", "reminder")
    description = ("Invest in tooling: automate repetitive/error-prone work into a "
                   "script/target/helper rather than repeating it by hand; improve "
                   "shared tooling over one-off workarounds -- without "
                   "over-engineering. Draft: reminder-led.")


class TechnicalWriter(Discipline):
    codename = "techwrite"
    name = "Technical Writer"
    default_enabled = False
    requires = ("hyg",)               # implies Generative Hygiene is on (does not extend it)
    action = "nudge"
    reminder = ("Technical Writer active: write for a READER, not for yourself -- "
                "lead with the point, stay concise and concrete, define a term "
                "before using it, prefer active voice and ONE consistent name per "
                "concept, and structure with headings, lists, and examples. Show "
                "with an example rather than telling; cut filler, hedging, and "
                "restatement.")
    OVERRIDABLE = ("default_enabled", "action", "reminder")
    description = ("Clear technical writing: lead with the conclusion, write for "
                   "the reader's context, stay concise and concrete, define terms, "
                   "prefer active voice and consistent terminology, and structure "
                   "with headings/lists/examples. Applies to docs, READMEs, and "
                   "commit/PR prose. Draft: reminder-led.")


DISCIPLINES = [IsoTree, HumanAccountability, Scratch, Promotion,
               GenerativeHygiene, FrozenFeatures, TestDrivenDevelopment,
               FeatureSpike, Performance, TacticalRetreat, Dreamer, Scientist,
               Stepwise, Consensus, Groomer, Toolsmith, TechnicalWriter]


def by_codename(codename):
    return next((d for d in DISCIPLINES if d.codename == codename), None)


def resolve(token):
    """Map a NAME (preferred) or CODENAME to the canonical codename."""
    t = token.lower()
    for d in DISCIPLINES:
        if t in (d.name.lower(), d.codename.lower()):
            return d.codename
    return t                                # unknown -> lowercased token


def defaults():
    """Codenames whose (possibly-overridden) default_enabled is truthy."""
    return {d.codename for d in DISCIPLINES if d.get("default_enabled")}


def closure(codenames):
    """Expand codenames with their transitive `requires` closure (cycle-safe).
    Enabling A therefore also activates everything A requires."""
    out, stack = set(), list(codenames)
    while stack:
        cn = stack.pop()
        if cn in out:
            continue
        out.add(cn)
        d = by_codename(cn)
        if d:
            stack.extend(d.requires)
    return out
