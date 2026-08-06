#!/usr/bin/env python3
"""CSOP discipline definitions.

A discipline is a singleton class whose identity and default properties live in
code, never in config. A project's `.claude/csop.json` may override only the
properties listed in `overridable`, replacing the default or, for a property in
`append`, adding to it. Gates read the effective value via `<Discipline>.get(key)`.
Layering, merge modes, and the `action` slot: docs/gate-internals.md.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402  (substrate: project_config loader)


class _Ref:
    """A read-through handle to a sibling discipline for reminder templates:
    `{codename.var}` resolves to that sibling's own effective value (its default
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
    conflicts = ()                           # codenames mutually exclusive with this one
    nudge = ""                               # pre-turn context (prevent wrong behavior this turn)
    reminder = ""                            # post-turn context (flag follow-up tasks)
    overridable = ("default_enabled", "nudge", "reminder")   # props a project may override
    append = ("nudge", "reminder")           # overridable props whose override is
                                             # appended to the code default, not replaced

    @classmethod
    def get(cls, key):
        """Effective value, layered code default < project override < current-stage
        override, for an overridable `key`. Project override comes from
        `.claude/csop.json[codename]`; the stage override is the current stage's
        `disciplines[codename]` object (see csop.stage_discipline). append props
        append at each layer; others replace."""
        val = getattr(cls, key)
        if key in cls.overridable:
            for layer in (csop.project_config().get(cls.codename, {}),
                          csop.stage_discipline(cls.codename)):
                if isinstance(layer, dict) and key in layer:
                    val = cls._append(val, layer[key]) if key in cls.append else layer[key]
        return val

    @staticmethod
    def _append(default, extra):
        if isinstance(default, str) and isinstance(extra, str):
            return (default + "\n" + extra) if default else extra
        if isinstance(default, list) and isinstance(extra, list):
            return default + extra
        return extra

    @classmethod
    def _params(cls):
        """This discipline's effective params (overridable minus the text fields
        `nudge`/`reminder`) -- the substitution context for templated text."""
        return {k: cls.get(k) for k in cls.overridable if k not in ("nudge", "reminder")}

    @classmethod
    def render(cls, key):
        """`get(key)`, then str.format it JIT against the effective config: this
        discipline's own params at top level, plus every discipline as a sibling
        handle keyed by codename, so a reminder can reference another discipline
        directly, e.g. `{hacc.deny_list}` or `{scratch.home}`. A list value (e.g. an
        array of nudges) is rendered element-wise. Fail-open: an unknown/broken
        placeholder leaves the text literal so a config typo can never brick a hook."""
        text = cls.get(key)
        ctx = dict(cls._params())
        for d in DISCIPLINES:
            ctx[d.codename] = _Ref(d)

        def fmt(s):
            if not isinstance(s, str):
                return s
            try:
                return s.format(**ctx)
            except Exception:
                return s
        if isinstance(text, list):
            return [fmt(s) for s in text]
        return fmt(text)


class IsoTree(Discipline):
    codename = "iso"
    name = "IsolatedTree"
    default_enabled = False
    home = "scratch/iso/"
    nudge = ("IsolatedTree active: prototype risky/exploratory/experimental "
                "changes to core in an iso-tree under the iso dir `{home}`, never "
                "/tmp; iterate + test there, then port only the proven diff back "
                "to core -- don't edit core in place for exploratory work. Use a "
                "fresh tree per task -- never reuse an existing tree (its state is "
                "unknown: stale or WIP); begin a new task with `git worktree add "
                "{home}<new> <clean-base>`.")
    reminder = ("IsolatedTree follow-up: if an experiment proved out, port the "
                "clean diff back to core by edits and tear down the tree under "
                "`{home}`; if it failed, discard the tree. Don't leave iso-trees "
                "lying around.")
    overridable = ("default_enabled", "home", "nudge", "reminder")
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
    nudge = ("Human Accountability active: git is read-only for you -- don't "
                "commit/stash/checkout/push/reset/rm/etc; ask the human to run "
                "git writes. exception when iso is active: git history ops "
                "confined to an iso tree are allowed (`git -C {iso.home}<name> "
                "rebase <core>` for freshness). never merge/commit into core -- "
                "promote a tree by edits/inserts. Git reads and `git add` are fine.")
    overridable = ("default_enabled", "deny_list", "nudge")
    description = ("Git is read-only for the agent: the git subcommands in "
                  "`deny_list` are denied. Git reads and `git add` (staging) "
                  "pass through. A human must run git writes directly (or lift "
                  "via CSOP_HACC=off); the agent cannot alter history / branches "
                  "/ working-tree / remote. When `iso` is active, git history ops "
                  "confined to an iso tree (rebase-for-freshness) are exempt -- "
                  "they cannot commit into core; promotion into core is by edits, "
                  "never a git merge.")


class Scratch(Discipline):
    codename = "scratch"
    name = "Scratch"
    default_enabled = True
    home = "scratch/"                 # move content here instead of destroying it
    # irreversibly destructive commands, denied; a project may replace the list.
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
    nudge = ("Scratch active: destructive operations are discouraged/disabled "
                "-- take content out of circulation by moving it to `{home}` "
                "instead of deleting it.")
    overridable = ("default_enabled", "deny_patterns", "home", "nudge")
    description = ("Discourages/denies irreversibly destructive commands: "
                   "dangerous recursive+force file removal and the 'nuclear "
                   "options' in git (reset --hard, clean -f, force push, "
                   "checkout ., branch -D, stash drop/clear, reflog expire, "
                   "filter-branch/repo), plus shred/mkfs/dd. The safe alternative "
                   "is to move content out of circulation into `home`. "
                   "Match rules + home are project-overridable.")


# the disciplines below are awareness-only; see `action` in the module docstring.

class Promotion(Discipline):
    codename = "pro"
    name = "Promotion"
    default_enabled = False
    nudge = ("Promotion active: work flows forward through stages. Declare the "
                "stage you are in with `/csop stage <name>`, and enter a later "
                "stage only as a promotion from one of its `from` sources. New work "
                "starts in an entry stage (a demo or an iso tree), not in core.")
    overridable = ("default_enabled", "nudge")
    description = ("Staged promotion flow over the top-level `stages` map. One "
                   "current stage per session (a sticky latch set by `/csop stage`, "
                   "seeded from a stage's `default_stage`), a `from`-DAG of legal "
                   "sources, and per-stage `pre`/`post` prompts. Entering a stage "
                   "with no active `from` source fires its `pre`; `post` fires after "
                   "edits. Per-stage `disciplines` overrides apply whenever a current "
                   "stage is set, independently of `pro`. Gate: promotion over edits.")


class GenerativeHygiene(Discipline):
    codename = "hyg"
    name = "Generative Hygiene"
    default_enabled = True
    max_comment_lines = 1             # >this added comment lines in a run -> reject
    notes_dir = "scratch/"            # externalize chain-of-thought here, not in code
    # prose file extensions: out of scope, since this gate judges code comments.
    prose_exts = ["md", "markdown", "mdx", "rst", "txt", "adoc", "org"]
    prose_dirs = ["docs/"]            # whole subtrees treated as prose
    # line-comment markers per file type; empty means the language has none.
    comment_markers = {
        "py": ["#"], "pyi": ["#"], "sh": ["#"], "bash": ["#"], "zsh": ["#"],
        "fish": ["#"], "rb": ["#"], "pl": ["#"], "r": ["#"], "jl": ["#"],
        "yaml": ["#"], "yml": ["#"], "toml": ["#"], "ini": ["#", ";"],
        "cfg": ["#", ";"], "conf": ["#"], "gitignore": ["#"], "dockerfile": ["#"],
        "makefile": ["#"], "mk": ["#"], "tf": ["#"], "nix": ["#"], "ps1": ["#"],
        "js": ["//"], "mjs": ["//"], "cjs": ["//"], "jsx": ["//"], "ts": ["//"],
        "tsx": ["//"], "c": ["//"], "h": ["//"], "cc": ["//"], "cpp": ["//"],
        "hpp": ["//"], "java": ["//"], "cs": ["//"], "go": ["//"], "rs": ["//"],
        "swift": ["//"], "kt": ["//"], "kts": ["//"], "scala": ["//"],
        "php": ["//", "#"], "dart": ["//"], "proto": ["//"], "sol": ["//"],
        "css": [], "html": [], "htm": [], "xml": [], "svg": [], "json": [],
        "scss": ["//"], "sass": ["//"], "less": ["//"],
        "sql": ["--"], "lua": ["--"], "hs": ["--"], "elm": ["--"], "ada": ["--"],
        "el": [";"], "lisp": [";"], "clj": [";"], "cljs": [";"], "scm": [";"],
        "rkt": [";"], "asm": [";"], "s": [";"],
        "vim": ['"'], "bat": ["::", "rem"], "cmd": ["::", "rem"],
        "tex": ["%"], "erl": ["%"], "m": ["%"], "matlab": ["%"],
    }
    unknown_markers = ["#", "//"]     # markers for a file type not in the table
    # tunable, language-agnostic detection of code syntax inside a comment.
    syntax_rules = [
        r"[)\]\w]\(",                 # call: token immediately before '(' (no space)
        r"\$\{|\$\(|\$\w",            # shell/make sigils
        r"=>|->|::|==|!=|&&|\|\|",    # code operators
        r"[{}]",                      # braces
    ]
    # bare all-caps words allowed in comments (acronyms/markers, not shouting)
    shout_ok = ["CSOP", "SOP", "CLI", "API", "URL", "JSON", "HTML", "HTTP", "ID",
                "ANSI", "SGR", "OSC", "UTF", "ASCII", "JIT", "WIP", "TODO", "FIXME",
                "NOTE", "OK", "SSOT", "MCP", "VM", "README", "LICENSE",
                "TCP", "UDP", "NTP", "DNS", "SSH", "TLS", "SSL", "IP", "MAC",
                "LAN", "WAN", "VPN", "FTP", "SMTP", "IMAP", "RPC", "GUI", "CPU",
                "GPU", "RAM", "OS", "DB", "SQL", "XML", "YAML", "CSV", "PDF",
                "CSS", "AWS", "GCP", "IAM", "ACL", "CRUD", "REST", "JWT", "CI",
                "CD", "QA", "UI", "UX", "EOF", "EOL", "PR", "TTY", "PID", "PATH",
                "DAG", "JSONC", "SVG", "PNG", "PDF", "ENV", "DIR", "CWD"]
    # line-shaped documentation prefixes: the doc budget, not the comment one.
    doc_prefixes = ["##", "///"]
    doc_regions = [{"open": r'^\s*("""|\'\'\')', "close": r'"""|\'\'\''},
                   {"open": r"^\s*/\*", "close": r"\*/"},
                   {"open": r"^\s*\{%\s*comment", "close": r"\{%\s*endcomment"},
                   {"open": r"^\s*<!--", "close": r"-->"}]
    doc_max_comment_lines = 6          # budget for a documentation block
    action = "block"
    nudge = ("Generative Hygiene active: do not externalize chain-of-thought "
                "into code comments -- at most one comment line per block, no "
                "code syntax quoted in comments, and no shouted words anywhere in "
                "a comment or docstring (all-caps for emphasis; a real global or "
                "env-var keeps its underscores and is fine). Keep running notes / reasoning in a dedicated notes or "
                "spike doc under `{notes_dir}`; delete cruft, don't comment it out.")
    overridable = ("default_enabled", "max_comment_lines", "notes_dir",
                   "syntax_rules", "shout_ok", "action", "nudge",
                   "doc_prefixes", "doc_regions", "doc_max_comment_lines",
                   "prose_exts", "prose_dirs", "comment_markers",
                   "unknown_markers")
    # a project's shout_ok / prose_exts / prose_dirs add to the built-in list
    append = ("nudge", "reminder", "shout_ok", "prose_exts", "prose_dirs")
    description = ("Comment hygiene on agent-generated code: rejects adding more "
                   "than `max_comment_lines` comment lines in a block, code syntax "
                   "(per `syntax_rules`) inside a comment, or a shouted all-caps "
                   "word (emphasis; globals/env-vars keep underscores and pass, or "
                   "add to `shout_ok`). Two budgets, split by marker shape: a "
                   "comment attached to code gets `max_comment_lines`, while "
                   "documentation -- a `doc_prefixes` line or a `doc_regions` "
                   "region -- gets `doc_max_comment_lines` and skips the syntax "
                   "rule. Neither is unlimited, and a block is judged at its "
                   "resulting size, so it cannot be grown past budget by repeated "
                   "appends. Where a block sits relative to what it documents is "
                   "language-specific, so the gate does not guess at it. The shout "
                   "rule ignores the split, since prose a human reads does not "
                   "shout. Pushes "
                   "chain-of-thought out of code into a notes/spike doc under "
                   "`notes_dir`. Prose/notes files are out of scope. "
                   "Language-agnostic; the rule lists are tunable.")


class FrozenFeatures(Discipline):
    codename = "freeze"
    name = "Frozen Features"
    default_enabled = False
    frozen = []                       # entries: a path fragment, or a mapping (see below)
    mode = "no-write"                 # default protection applied to a bare-path entry
    action = "block"
    nudge = ("Frozen Features active: the frozen paths are off-limits. A "
                "no-write path must not be modified (reads are fine); a no-touch "
                "path must not even be read -- it is a generated/build-artifact "
                "copy, so reading the stale copy is itself a trap; use the source "
                "instead. A no-restructure path may be edited in place, but never "
                "moved or removed by shell (rm/mv/cp). Some entries protect only a "
                "region of a file (marker regex, or a described section) -- leave "
                "that region unchanged. If a change is truly needed, propose it for "
                "a human.")
    overridable = ("default_enabled", "frozen", "mode", "action", "nudge")
    description = ("Protects frozen paths and file regions from access. Each "
                   "`frozen` entry is a path fragment (a file or a directory "
                   "subtree), or a mapping {path, mode, why, use, regex, prose, "
                   "exempt}. Whole-path modes: no-write (default) blocks "
                   "modification (tool edits and destructive shell verbs) while "
                   "reads pass; no-touch also blocks reads/Bash refs of a generated "
                   "copy; no-restructure lets in-place tool edits through but blocks "
                   "a destructive shell verb (rm/mv/cp) on the subtree. `exempt` "
                   "fragments skip the shell check (e.g. worktree copies). File "
                   "regions: `regex` markers hard-gate the matched span of a file; "
                   "`prose` describes a region as a soft nudge. A non-liftable rule "
                   "belongs in the harness deny-list, not this fail-open hook. "
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
    nudge = ("Test-Driven Development active: write a failing test first, then "
                "implement to green; don't change implementation without a "
                "matching test; run `{test_command}` after each change.")
    overridable = ("default_enabled", "test_globs", "src_globs", "test_command",
                   "action", "nudge")
    description = ("Tests-first workflow: a failing test precedes implementation; "
                   "implementation (`src_globs`) shouldn't change without a "
                   "matching test (`test_globs`); run `test_command` after "
                   "changes. Draft gate: nudge on src edits lacking a recent test "
                   "edit.")


class FeatureSpike(Discipline):
    codename = "spike"
    name = "Feature Spike"
    default_enabled = False
    home = Scratch.home + "spike/"    # derived from the sibling's home directly
    requires = ("hyg", "scratch")     # co-activate hygiene + the destructive-op guard
    action = "nudge"
    nudge = ("Feature Spike active: this is a time-boxed, throwaway "
                "exploration to de-risk/learn -- keep it in `{home}`, a spike "
                "subdir of Scratch's `{scratch.home}`; don't polish or "
                "productionize, and expect to discard and rewrite afterward.")
    reminder = ("Feature Spike follow-up: this was throwaway. Capture the lesson "
                "in a note, then discard the spike code in `{home}`; do not "
                "promote it as-is -- rewrite properly if the idea holds.")
    overridable = ("default_enabled", "home", "action", "nudge", "reminder")
    description = ("A time-boxed, throwaway exploratory spike to de-risk or learn "
                   "-- kept in `home` (derived from Scratch's `home`), "
                   "not polished/productionized, expected to be discarded. Requires "
                   "Generative Hygiene + Scratch. Complements IsolatedTree "
                   "(isolation) by governing investment. Draft: nudge-led.")


class Performance(Discipline):
    codename = "perf"
    name = "Performance"
    default_enabled = False
    benchmark_command = ""            # how to measure (project sets)
    action = "nudge"
    nudge = ("Performance active: measure before optimizing (don't guess) -- "
                "profile hot paths, watch for N+1 / quadratic / repeated work and "
                "avoidable allocations, keep within budgets, and don't regress. "
                "Optimize only what a measurement shows is hot.")
    overridable = ("default_enabled", "benchmark_command", "action", "nudge")
    description = ("Measure-first performance discipline: profile before "
                   "optimizing, avoid premature optimization, watch for "
                   "quadratic/N+1 patterns, guard against regressions via "
                   "`benchmark_command`. Draft: nudge-led.")


class TacticalRetreat(Discipline):
    codename = "tactical"
    name = "Tactical Retreat"
    default_enabled = False
    action = "nudge"
    nudge = ("Tactical Retreat active: when an approach stops working, retreat "
                "cleanly -- revert to the last known-good state and rethink "
                "instead of piling fixes on a failing direction. Recognize the "
                "dead end early; avoid flip/revert/flip churn.")
    overridable = ("default_enabled", "action", "nudge")
    description = ("When a change/experiment is going badly, cleanly retreat to a "
                   "known-good state and rethink instead of accumulating hacks or "
                   "churning flip/revert/flip. Draft: nudge-led (a nudge after "
                   "repeated failed retries).")


class Dreamer(Discipline):
    codename = "dream"
    name = "Dreamer"
    default_enabled = False
    home = Scratch.home               # writes are confined here while active
    action = "deny"
    nudge = ("Dreamer active: diverge, don't converge -- brainstorm freely, "
                "generate many options, defer judgment. Capture ideas as notes in "
                "`{home}`; structured writes outside `{home}` are denied -- think "
                "big / blue-sky, don't build yet.")
    overridable = ("default_enabled", "home", "action", "nudge")
    description = ("Ideation / divergent-thinking mode: generate options freely, "
                   "defer judgment and implementation, don't prematurely converge "
                   "or start building. Enforced: structured writes are confined to "
                   "`dir` (default the scratch area); writes elsewhere are denied. "
                   "The 'diverge' counterpart to the execution disciplines.")


class Scientist(Discipline):
    codename = "science"
    name = "Scientist"
    default_enabled = False
    requires = ("iso",)               # an experimentalist runs experiments in an iso-tree
    action = "nudge"
    nudge = ("Scientist active: observe first, then experiment -- don't assume. "
                "Look at the actual behavior and evidence, form one hypothesis, "
                "change one variable, predict the outcome, run it in an iso-tree "
                "under `{iso.home}`, and measure. Let evidence (not assumption) "
                "decide; reproduce before you conclude, and record what you tried.")
    overridable = ("default_enabled", "action", "nudge")
    description = ("Empirical method for an experimentalist: observe the actual "
                   "behavior before theorizing, form one hypothesis, change one "
                   "variable, predict and measure, let evidence decide, and "
                   "reproduce before concluding. Experiments run in an iso-tree "
                   "(requires IsolatedTree), so a failed experiment never touches "
                   "core. Guards against assumption-driven debugging.")


class Stepwise(Discipline):
    codename = "step"
    name = "Stepwise"
    default_enabled = False
    action = "nudge"
    nudge = ("Stepwise active: work in small, verifiable increments -- one "
                "change at a time, check it (build/test/run) before the next, and "
                "keep each step reversible. No big-bang edits; land a working step "
                "before starting the next.")
    overridable = ("default_enabled", "action", "nudge")
    description = ("Small-increment method: make one change at a time, verify "
                   "before proceeding, keep each step reversible; no large "
                   "multi-concern edits. Complements TDD/Scientist. Draft: "
                   "nudge-led (a nudge on large/multi-file edits).")


class Consensus(Discipline):
    codename = "consensus"
    name = "Consensus"
    default_enabled = False
    action = "nudge"
    nudge = ("Consensus active: don't rely on a single take -- corroborate "
                "before acting. Cross-check a claim against more than one source / "
                "angle, seek a second opinion on consequential decisions, and "
                "surface disagreement rather than papering over it.")
    overridable = ("default_enabled", "action", "nudge")
    description = ("Corroboration / multi-perspective method: cross-check claims "
                   "against more than one source or angle, seek a second opinion "
                   "on consequential decisions, and surface disagreement instead "
                   "of settling on the first plausible answer. Draft: "
                   "nudge-led.")


class Groomer(Discipline):
    codename = "groom"
    name = "Groomer"
    default_enabled = False
    conflicts = ("iso",)              # Groomer edits core in-place; IsolatedTree forbids that
    action = "nudge"
    nudge = ("Groomer active: this is a dedicated, behavior-preserving style "
                "sweep, not improve-as-you-go. Pick a target and pass over it on "
                "purpose; never fold grooming into unrelated work. In scope: "
                "naming, formatting, and comment cleanup for brevity and relevance, "
                "plus obviously-safe refactors. forbidden: any behavior change, and "
                "any bulk or mechanical pass (sed, a formatter, mass-rename) that "
                "hides the change. Make every edit explicit so the diff stays fully "
                "reviewable. You edit core in-place, so keep each step small and "
                "verifiable. When in doubt, don't.")
    overridable = ("default_enabled", "action", "nudge")
    description = ("Behavior-preserving style sweeps: a dedicated, bounded pass "
                   "over a chosen target for naming, formatting, comment cleanup "
                   "(brevity/relevance), and obviously-safe refactors. not "
                   "improve-as-you-go, and no behavior change. Every change is an "
                   "explicit, reviewable edit; no mechanical or bulk pass that "
                   "hides the diff. Edits core in-place, so it conflicts with "
                   "IsolatedTree (enabling one disables the other). Complements "
                   "Generative Hygiene by sweeping existing code.")


class Toolsmith(Discipline):
    codename = "smith"
    name = "Toolsmith"
    default_enabled = False
    action = "nudge"
    nudge = ("Toolsmith active: when a task is repetitive or error-prone, "
                "invest in the tool -- write a script/target/helper instead of "
                "doing it by hand again, and prefer improving shared tooling over "
                "one-off workarounds. Sharpen the axe, but don't gold-plate.")
    overridable = ("default_enabled", "action", "nudge")
    description = ("Invest in tooling: automate repetitive/error-prone work into a "
                   "script/target/helper rather than repeating it by hand; improve "
                   "shared tooling over one-off workarounds -- without "
                   "over-engineering. Draft: nudge-led.")


class TechnicalWriter(Discipline):
    codename = "techwrite"
    name = "Technical Writer"
    default_enabled = False
    requires = ("hyg",)               # implies Generative Hygiene is on (does not extend it)
    banned = [chr(0x2014), "earns its keep"]   # rejected substrings (em-dash, a cliche)
    discouraged = ["gate", "seam", "leverage", "seamless"]   # prose-only jargon: warned about, never blocked
    prose_globs = ["*.md", "*.markdown", "*.rst", "*.md.j2", "*.j2"]
    prose_rules = []             # project regexes for code leaking into doc prose
    token = "docs-code-ok"       # per-line opt-out marker in the doc source
    exempt = []                  # basenames skipped entirely (e.g. a form cheat-sheet)
    action = "deny"
    nudge = ("Technical Writer active: write for a reader, not for yourself -- "
                "lead with the point, stay concise and concrete, define a term "
                "before using it, prefer active voice and one consistent name per "
                "concept, and structure with headings, lists, and examples. Show "
                "with an example rather than telling; cut filler and hedging. Do "
                "not use em-dashes (a comma, colon, or period reads as human). In "
                "docs, keep runnable code in a fence or backticks, not in prose. "
                "Document the destination, never the journey: what the thing is "
                "and how to use it, not what you tried, measured, ruled out, or "
                "changed your mind about. A reader who was not there does not "
                "need the detour, and a finding that mattered belongs in a notes "
                "or spike doc under `{hyg.notes_dir}`, not in the docs.")
    overridable = ("default_enabled", "banned", "discouraged", "prose_globs",
                   "prose_rules", "token", "exempt", "action", "nudge")
    description = ("Clear technical writing: lead with the conclusion, stay concise "
                   "and concrete, prefer active voice, and structure with "
                   "headings/lists/examples. Enforced on added text: `banned` "
                   "substrings (default the em-dash) in any file, plus `prose_rules` "
                   "(project regexes) in `prose_globs` docs, where fenced blocks, "
                   "backtick spans, Jinja, HTML code regions, and tables are masked "
                   "first. A rule with `in_spans` also checks inside backticks; a "
                   "line carrying `token` opts out; `exempt` basenames are skipped. "
                   "`discouraged` words (default `gate`, `seam`, `leverage`, "
                   "`seamless`) warn in prose "
                   "without ever blocking. prose_rules empty by default.")


class EntrypointsSandbox(Discipline):
    codename = "entrypoints"
    name = "Entrypoints Sandbox"
    default_enabled = False
    entrypoints = []                  # blessed command prefixes the project sanctions
    reads = ["ls", "cat", "head", "tail", "less", "more", "grep", "egrep",
             "fgrep", "rg", "ag", "find", "fd", "tree", "wc", "stat", "file",
             "which", "type", "echo", "printf", "pwd", "cd", "sort", "uniq",
             "cut", "nl", "tac", "column", "diff", "cmp", "jq", "yq", "xxd",
             "od", "strings", "date", "whoami", "id", "uname", "hostname", "du",
             "df", "realpath", "readlink", "basename", "dirname", "test",
             "true", "false", "git status", "git log", "git diff", "git show",
             "git branch", "git rev-parse", "git remote", "git ls-files",
             "git blame"]
    action = "deny"
    nudge = ("Entrypoints Sandbox active: the shell is restricted to basic read "
                "commands and the project's blessed entrypoints -- don't run raw "
                "tools directly (use the sanctioned wrapper, e.g. `tox`/`make`, "
                "not bare `python`/`pip`). Blessed: {entrypoints}. Reads and edits "
                "are unaffected.")
    overridable = ("default_enabled", "entrypoints", "reads", "action", "nudge")
    append = ("nudge", "reads")
    description = ("Restricts the shell to basic read operations and the project's "
                   "blessed `entrypoints` -- a Bash allow-list (token-prefix "
                   "matched per pipeline segment) so the agent drives the "
                   "sanctioned wrapper (tox/make/npm) instead of raw tools like "
                   "bare python/pip. `entrypoints` is empty by default; a project "
                   "sets it. Reads and edits are unaffected. Gate: entrypoints "
                   "over Bash.")


class RobotAccountability(Discipline):
    codename = "racc"
    name = "Robot Accountability"
    default_enabled = False
    action = "deny"
    nudge = ("Robot Accountability active: make every file change through the Edit "
             "or Write tool so the human sees a diff. Don't sneak edits in with "
             "shell redirects, a heredoc, sed, tee, a patch, or an inline "
             "python/node script; those hide the change. Read-only shell is fine.")
    overridable = ("default_enabled", "action", "nudge")
    description = ("The agent must change files visibly: edits go through the "
                   "Edit/Write tool (which shows a diff), not in-place shell "
                   "mutations. Gate: a Bash command that writes a file in place "
                   "(sed -i, tee, dd, a redirect or heredoc to a file, a patch "
                   "applied by `patch` or git, a line editor, or an inline "
                   "`python -c`/`node -e` script that opens a file for writing) is "
                   "denied, so use the Edit tool. Closing that shell path is what "
                   "keeps the write-side gates (hygiene, technical writing) from "
                   "being sidestepped, since they only see Edit and Write. The "
                   "robot counterpart to Human Accountability.")


class Idiomatic(Discipline):
    codename = "idiom"
    name = "Idiomatic"
    default_enabled = False
    nudge = [
        "Match the surrounding code: naming, structure, comment density, and error "
        "handling should look like the file it lives in.",
        "Prefer the language's and the framework's standard idioms over clever or "
        "novel constructs.",
        "Reuse the helpers, patterns, and conventions already in this repo before "
        "introducing new ones.",
        "Keep a new file consistent with its siblings; do not invent a private style "
        "for one corner of the tree.",
    ]
    reject = []                       # [{pattern, message}] regexes rejected in added text
    action = "deny"
    overridable = ("default_enabled", "nudge", "reject", "action")
    description = ("Nudges the agent to write code that matches the surrounding "
                   "conventions and the language/framework idioms. `nudge` is an array "
                   "of prompts, each injected as its own pre-turn line (a project's "
                   "`nudge` array appends). Optional enforcement: `reject` is a list of "
                   "{pattern, message} regexes; an added line matching one is rejected "
                   "at `action`. Empty `reject` by default (awareness-only). Gate: idiom "
                   "over Edit/Write/MultiEdit.")


class FileTypeHooks(Discipline):
    codename = "file-hooks"
    name = "File-Type Hooks"
    default_enabled = False
    types = []                        # [{match:[globs], reminder?, command? (with {file})}]
    nudge = ("File-Type Hooks active: editing certain file types triggers a "
             "per-type reminder or a project command whose output comes back to "
             "you after the edit. Treat that returned output as ground truth for "
             "the file you just touched.")
    overridable = ("default_enabled", "types", "nudge")
    description = ("Per file type, inject a reminder and/or run a project command "
                   "after an edit. Each `types` entry is a `match_globs` list with "
                   "an optional `reminder` (pure context injection) and an optional "
                   "`command` (a shell command; its captured output fed back to you). "
                   "`{file}` expands to the edited path in both. Empty by default; a "
                   "project sets it. Runs on PostToolUse, the only event that can "
                   "return command output to the model. Gate: file-hooks over "
                   "Edit/Write/MultiEdit/NotebookEdit.")


DISCIPLINES = [IsoTree, HumanAccountability, RobotAccountability, Scratch,
               Promotion, GenerativeHygiene, FrozenFeatures, TestDrivenDevelopment,
               FeatureSpike, Performance, TacticalRetreat, Dreamer, Scientist,
               Stepwise, Consensus, Groomer, Toolsmith, TechnicalWriter,
               EntrypointsSandbox, FileTypeHooks, Idiomatic]


def by_codename(codename):
    return next((d for d in DISCIPLINES if d.codename == codename), None)


def resolve(token):
    """Map a name (preferred) or codename to the canonical codename."""
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


def conflicts(codename):
    """Codenames mutually exclusive with `codename` (symmetric): enabling one
    disables the other. A conflict declared on either side of the pair counts."""
    out = set()
    d = by_codename(codename)
    if d:
        out.update(d.conflicts)
    for x in DISCIPLINES:
        if codename in x.conflicts:
            out.add(x.codename)
    return out


def dependents(codenames):
    """Codenames that transitively require any of `codenames` (the reverse of
    `closure`). Dropping a discipline must also drop these, or they would be left
    active without a requirement they depend on."""
    targets = set(codenames)
    return {x.codename for x in DISCIPLINES
            if (closure({x.codename}) - {x.codename}) & targets}
