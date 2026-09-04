#!/usr/bin/env python3
"""Offline test suite for CSOP: static sanity plus gate/CLI behavior.

Stdlib-only, no live session needed: each hook is subprocessed with a synthetic
event on stdin, exactly as the harness would invoke it. Run `make test`. Note
that the version-control and em-dash strings below are data, not commands, so
this repo's own live gates never see them.
"""
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
sys.path.insert(0, HOOKS)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import csop            # noqa: E402
import disciplines     # noqa: E402
import sync_commands   # noqa: E402

EM_DASH = chr(8212)

# a command file shaped the way sync_commands writes them
_CMD = ('---\ndescription: t\nallowed-tools: Bash(python3 '
        '"${CLAUDE_PLUGIN_ROOT}/hooks/csop.py" *)\n---\n'
        '!`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/csop.py" $ARGUMENTS`\n%s')


def _env(**extra):
    e = dict(os.environ)
    e["CLAUDE_PLUGIN_DATA"] = tempfile.mkdtemp()
    e["CLAUDE_SESSION_ID"] = "t"
    e.update(extra)
    return e


def _cli(args, env):
    return subprocess.run([sys.executable, os.path.join(HOOKS, "csop.py")] + args,
                          capture_output=True, cwd=ROOT, env=env)


def _gate(name, event, env):
    return subprocess.run([sys.executable, os.path.join(HOOKS, name)],
                          input=json.dumps(event).encode(),
                          capture_output=True, cwd=ROOT, env=env)


def _denied(cp):
    return cp.returncode == 2 or b'"deny"' in cp.stdout


def _write(path, body):
    with open(path, "w") as f:
        f.write(body)


def _project(cfg, files=None):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, ".claude"))
    _write(os.path.join(d, ".claude", "csop.json"), json.dumps(cfg))
    for rel, body in (files or {}).items():
        _write(os.path.join(d, rel), body)
    return d


def _wr(path, body):
    """A Write tool event for `path`."""
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": body}}


def _bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


def _edit(path=None, old="x", new="y"):
    ti = {"old_string": old, "new_string": new}
    if path is not None:
        ti["file_path"] = path
    return {"tool_name": "Edit", "tool_input": ti}


class StaticChecks(unittest.TestCase):
    def test_hooks_parse(self):
        for f in sorted(os.listdir(HOOKS)):
            if f.endswith(".py"):
                with open(os.path.join(HOOKS, f)) as fh:
                    ast.parse(fh.read())

    def test_json_valid(self):
        for rel in (".claude-plugin/plugin.json", "hooks/hooks.json",
                    ".claude/settings.json"):
            with open(os.path.join(ROOT, rel)) as f:
                json.load(f)

    def test_jsonc_valid(self):
        with open(os.path.join(ROOT, ".claude", "csop.json")) as f:
            csop.loads_jsonc(f.read())

    def test_tools_parse(self):
        td = os.path.join(ROOT, "tools")
        for f in (sorted(os.listdir(td)) if os.path.isdir(td) else []):
            if f.endswith(".py"):
                with open(os.path.join(td, f)) as fh:
                    ast.parse(fh.read())


class ConfigChecks(unittest.TestCase):
    def test_requires_graph_resolves(self):
        for x in disciplines.DISCIPLINES:
            for r in x.requires:
                self.assertIsNotNone(disciplines.by_codename(r), (x.codename, r))

    def test_conflicts_graph_resolves(self):
        for x in disciplines.DISCIPLINES:
            for c in x.conflicts:
                self.assertIsNotNone(disciplines.by_codename(c), (x.codename, c))

    def test_no_unresolved_placeholders(self):
        import re as _re
        for d in disciplines.DISCIPLINES:
            for key in ("nudge", "reminder"):
                out = d.render(key)
                if isinstance(out, str):
                    self.assertIsNone(_re.search(r"\{[A-Za-z_][\w.]*\}", out),
                                      "{0}.{1} has an unresolved placeholder".format(d.codename, key))

    def test_sibling_ref(self):
        self.assertTrue(disciplines.FeatureSpike.home.startswith(
            disciplines.Scratch.home))
        self.assertIn("scratch/", disciplines.FeatureSpike.render("nudge"))

    def test_merge_settings_idempotent(self):
        dest = os.path.join(tempfile.mkdtemp(), "settings.json")
        _write(dest, json.dumps({"permissions": {"allow": ["Bash(ls *)"]},
                                 "hooks": {"PreToolUse": []}}))
        merge = os.path.join(ROOT, "tools", "merge_settings.py")
        hooks = os.path.join(ROOT, "hooks", "hooks.json")
        run = lambda: subprocess.run([sys.executable, merge, dest, ".claude/csop",
                                      hooks], capture_output=True, cwd=ROOT)
        run()
        with open(dest) as f:
            cfg = json.load(f)
        self.assertIn("Bash(ls *)", cfg["permissions"]["allow"])              # preserved
        self.assertIn('Bash(python3 "${CLAUDE_PROJECT_DIR}/.claude/csop/hooks/csop.py" *)',
                      cfg["permissions"]["allow"])                            # pre-approves /sop, cwd-safe
        self.assertTrue(cfg["hooks"]["PreToolUse"])                          # our hooks merged
        before = json.dumps(cfg, sort_keys=True)
        run()
        with open(dest) as f:
            self.assertEqual(before, json.dumps(json.load(f), sort_keys=True))  # idempotent


class ShellChecks(unittest.TestCase):
    """The shared shell-scan substrate the write-side gates agree on."""

    DEL = chr(114) + chr(109)          # spelled so the live gates read this as data

    def test_write_constructs_named(self):
        for cmd, name in (("sed -i s/a/b/ f.py", "sed -i"),
                          ("echo hi > f.py", "redirect"),
                          ("printf x | tee f.py", "tee"),
                          ("patch -p1 < fix.diff", "patch"),
                          ("python3 -c \"open('f','a').write('x')\"", "inline script")):
            self.assertIn(name, csop.write_constructs(cmd), cmd)
        for cmd in ("cat f.py", "grep x f.py 2>/dev/null", "pip install requests",
                    self.DEL + " -f f.py"):
            self.assertEqual(csop.write_constructs(cmd), [], cmd)

    def test_mutates_files_is_the_broad_question(self):
        for cmd in ("sed -i s/a/b/ f.py", "echo hi > f.py", self.DEL + " -f f.py",
                    "mv a b", "cp a b", "touch a", "mkdir -p a/b"):
            self.assertTrue(csop.mutates_files(cmd), cmd)
        for cmd in ("cat f.py", "grep x f.py", "pip install requests"):
            self.assertFalse(csop.mutates_files(cmd), cmd)

    def test_gates_do_not_keep_private_copies(self):
        for name in ("csop-gate-racc.py", "csop-gate-isowrite.py",
                     "csop-gate-pathblock.py"):
            with open(os.path.join(HOOKS, name)) as f:
                src = f.read()
            self.assertNotIn("_MUTATORS", src, name)
            self.assertNotIn("_MUTATE ", src, name)


class CliChecks(unittest.TestCase):
    def test_catalog_is_an_index_and_show_is_the_full_entry(self):
        env = _env(); _cli(["enable", "iso"], env)
        cat = _cli(["catalog"], env)
        self.assertEqual(cat.returncode, 0)
        rows = [ln for ln in cat.stdout.decode().splitlines() if "  " in ln]
        for row in rows:
            self.assertLessEqual(len(row), 80)         # one screen, no wrapping
        self.assertTrue(any(ln.startswith("* iso") for ln in rows))   # active, starred
        self.assertTrue(any(ln.startswith("  tdd") for ln in rows))   # inactive, plain
        full = _cli(["show", "Memory Accountability"], env).stdout.decode()
        self.assertIn("requires: racc", full)
        self.assertIn("allow_retraction", full)        # the config keys are listed
        flat = " ".join(full.split())                  # wrapped, so match unwrapped
        self.assertIn("a memory can still form but never in silence", flat)
        self.assertEqual(_cli(["show", "nope"], env).returncode, 2)

    def test_read_only_slash_commands_answer_without_the_model(self):
        env = _env(); _cli(["enable", "iso"], env)
        tag = ("<command-message>sop</command-message>\n"
               "<command-name>/sop</command-name>\n"
               "<command-args>{0}</command-args>")
        def ask(args):
            cp = _gate("csop-command.py", {"hook_event_name": "UserPromptSubmit",
                                           "prompt": tag.format(args)}, env)
            return cp.stdout.decode()
        cat = json.loads(ask("catalog"))
        self.assertEqual(cat["decision"], "block")       # blocked, so nothing is queried
        self.assertTrue(cat["suppressOriginalPrompt"])   # and no prompt echo trails it
        self.assertIn("* iso", cat["reason"])
        self.assertIn("Human Accountability", json.loads(ask("show hacc"))["reason"])
        self.assertIn("active:", json.loads(ask(""))["reason"])   # no verb means list
        self.assertEqual(ask("enable iso"), "")          # mutating: keeps its prompt
        self.assertEqual(ask("stage core"), "")
        plain = _gate("csop-command.py", {"hook_event_name": "UserPromptSubmit",
                                          "prompt": "please read /sop and report"}, env)
        self.assertEqual(plain.stdout.decode(), "")      # prose is never a command

    def test_enable(self):
        self.assertIn("iso", _cli(["enable", "iso"], _env()).stdout.decode())

    def test_help_is_a_command_not_an_error(self):
        cp = _cli(["help"], _env())
        self.assertEqual(cp.returncode, 0)
        self.assertIn("catalog", cp.stdout.decode())        # help goes to stdout
        bad = _cli(["bogus"], _env())
        self.assertEqual(bad.returncode, 2)
        self.assertIn("unknown command", bad.stderr.decode())

    def test_modeline_points_at_help(self):
        env = _env(NO_COLOR="1"); _cli(["enable", "iso"], env)
        out = subprocess.run(
            [sys.executable, "-c",
             "import sys;sys.path.insert(0,%r);"
             "import importlib.util as u;"
             "s=u.spec_from_file_location('m',%r);m=u.module_from_spec(s);"
             "s.loader.exec_module(m);print(m.render())" % (
                 HOOKS, os.path.join(HOOKS, "csop-modeline.py"))],
            capture_output=True, cwd=ROOT, env=env).stdout.decode()
        head = out.strip().splitlines()[0]
        self.assertIn("/sop help", head)                   # the hint rides the head line
        self.assertNotIn("Usage:", out)                     # no usage list to drift
        lines = out.strip().splitlines()
        for line in lines:
            self.assertRegex(line[:2], r"^\W\s$")           # one glyph, then a space
            self.assertLessEqual(len(line), 58)             # never long enough to wrap
        gutter = {line[0] for line in lines}
        self.assertLessEqual(len(gutter), 3)                # corner, rail, corner
        for glyph in gutter:
            self.assertLessEqual(0x2500, ord(glyph))        # all from one box family
            self.assertLessEqual(ord(glyph), 0x257f)
        for line in lines[1:-1]:
            self.assertEqual(line[0], lines[1][0])          # one rail carries the middle
        self.assertNotIn("(", lines[1])                     # no parenthesis wrappers

    def test_modeline_marks_the_current_stage(self):
        proj = _project({"stages": {"spike": {}, "core": {"from": ["spike"]}}})
        env = _env(NO_COLOR="1", CLAUDE_PROJECT_DIR=proj)
        _cli(["enable", "pro"], env)
        render = lambda: subprocess.run(
            [sys.executable, "-c",
             "import sys;sys.path.insert(0,%r);"
             "import importlib.util as u;"
             "s=u.spec_from_file_location('m',%r);m=u.module_from_spec(s);"
             "s.loader.exec_module(m);print(m.render())" % (
                 HOOKS, os.path.join(HOOKS, "csop-modeline.py"))],
            capture_output=True, cwd=proj, env=env).stdout.decode()
        self.assertIn("(none current)", render())      # no stage set yet
        _cli(["stage", "core"], env)
        out = render()
        self.assertIn("Active Stage :: core", out)     # the stage you are in,
        self.assertNotIn("spike", out)                 # not the roster around it
        self.assertEqual(out.strip().splitlines()[-1][2:],
                         "Active Stage :: core")       # and it closes the footer
        self.assertNotIn("(none current)", out)

    def test_modeline_sends_reminders_to_the_agent_and_the_box_to_the_human(self):
        env = _env(NO_COLOR="1"); _cli(["enable", "iso"], env)
        stop = {"hook_event_name": "Stop"}
        first = json.loads(_gate("csop-modeline.py", stop, env).stdout.decode())
        self.assertIn("IsolatedTree follow-up",
                      first["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("systemMessage", first)       # the human's channel stays clean
        stop["stop_hook_active"] = True
        back = json.loads(_gate("csop-modeline.py", stop, env).stdout.decode())
        self.assertIn("Active Disciplines", back["systemMessage"])
        self.assertNotIn("follow-up", back["systemMessage"])
        self.assertNotIn("hookSpecificOutput", back)   # one handback, never a loop

    def test_requires_closure(self):
        self.assertIn("hyg", _cli(["enable", "techwrite"], _env()).stdout.decode())

    def test_disable_is_the_inverse_of_enable(self):
        env = _env(); _cli(["enable", "iso"], env)
        cp = _cli(["disable", "iso"], env)
        self.assertEqual(cp.returncode, 0)
        self.assertIn("disabled: iso", cp.stdout.decode())
        self.assertNotIn("iso", _cli(["list"], env).stdout.decode())

    def test_disable_drops_dependents_and_all(self):
        env = _env(); _cli(["enable", "techwrite"], env)
        out = _cli(["disable", "hyg"], env).stdout.decode()
        self.assertIn("techwrite", out.split("disabled:")[1])   # requires hyg, so it goes too
        _cli(["enable", "iso"], env)
        self.assertEqual(_cli(["disable", "all"], env).returncode, 0)
        self.assertEqual(_cli(["list"], env).stdout.decode().strip(), "active:")

    def test_disable_of_an_inactive_discipline_is_an_error(self):
        self.assertEqual(_cli(["disable", "iso"], _env()).returncode, 1)


class GateChecks(unittest.TestCase):
    def test_bashverb_blocks_tmp_worktree(self):
        env = _env(); _cli(["enable", "iso"], env)
        cp = _gate("csop-gate-bashverb.py", _bash("git worktree add /tmp/x HEAD"), env)
        self.assertEqual(cp.returncode, 2)

    def test_iso_write_ownership(self):
        env = _env(); _cli(["enable", "iso"], env)
        target = _edit(path="scratch/iso/mk/x")
        self.assertEqual(_gate("csop-gate-isowrite.py", target, env).returncode, 2)
        _gate("csop-gate-bashverb.py", _bash("git worktree add scratch/iso/mk HEAD"), env)
        self.assertEqual(_gate("csop-gate-isowrite.py", target, env).returncode, 0)

    def test_hacc_iso_sandbox(self):
        env = _env(); _cli(["enable", "hacc"], env); _cli(["enable", "iso"], env)
        self.assertTrue(_denied(_gate("csop-gate-git.py", _bash("git commit -m x"), env)))
        self.assertFalse(_denied(_gate("csop-gate-git.py",
                         _bash("git -C scratch/iso/mk rebase main"), env)))
        self.assertTrue(_denied(_gate("csop-gate-git.py",
                        _bash("git -C scratch/iso/mk push"), env)))

    def test_hacc_reads_survive_unrelated_clauses(self):
        env = _env(); _cli(["enable", "hacc"], env)
        for cmd in ("git log --oneline && make " + "clean",
                    "git status && " + "rm -f scratch/tmp",
                    "git worktree add scratch/iso/mk HEAD && ls"):
            self.assertFalse(_denied(_gate("csop-gate-git.py", _bash(cmd), env)), cmd)

    def test_hacc_exemption_is_per_invocation(self):
        env = _env(); _cli(["enable", "hacc"], env); _cli(["enable", "iso"], env)
        # an iso-scoped read must not clear a core write beside it
        cmd = "git -C scratch/iso/mk log && git " + "reset --hard"
        self.assertTrue(_denied(_gate("csop-gate-git.py", _bash(cmd), env)))
        self.assertTrue(_denied(_gate("csop-gate-git.py", _bash("git $CMD"), env)))

    def test_hacc_worktree_reads_only(self):
        env = _env(); _cli(["enable", "hacc"], env)
        for cmd in ("git worktree list", "git worktree add scratch/iso/mk HEAD"):
            self.assertFalse(_denied(_gate("csop-gate-git.py", _bash(cmd), env)), cmd)
        for cmd in ("git worktree " + "remove scratch/iso/mk",
                    "git worktree " + "prune"):
            self.assertTrue(_denied(_gate("csop-gate-git.py", _bash(cmd), env)), cmd)

    def test_orphan_config_key_is_inert(self):
        proj = _project({"dream": {"default_enabled": True, "home": "x/"},
                         "hacc": {"default_enabled": True}})
        env = _env(CLAUDE_PROJECT_DIR=proj)
        self.assertEqual(_cli(["list"], env).returncode, 0)
        self.assertEqual(_cli(["catalog"], env).returncode, 0)
        self.assertNotEqual(_cli(["enable", "dream"], env).returncode, 0)

    def test_freeze_region(self):
        proj = _project(
            {"freeze": {"default_enabled": True,
                        "frozen": [{"path": "conf.py", "regex": "# FROZEN.*# END"}]}},
            {"conf.py": "a\n# FROZEN\nsecret=1\n# END\nb\n"})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "freeze"], env)
        inside = _edit(path="conf.py", old="secret=1")
        outside = _edit(path="conf.py", old="a")
        self.assertEqual(_gate("csop-gate-pathblock.py", inside, env).returncode, 2)
        self.assertEqual(_gate("csop-gate-pathblock.py", outside, env).returncode, 0)

    def test_freeze_no_restructure(self):
        proj = _project({"freeze": {"default_enabled": True, "frozen": [
            {"path": ".cmk/", "mode": "no-restructure",
             "exempt": ["scratch/iso/"]}]}})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "freeze"], env)
        # in-place tool edit inside the subtree passes
        self.assertEqual(_gate("csop-gate-pathblock.py",
                         _edit(path=".cmk/x.mk"), env).returncode, 0)
        # a read of the subtree passes
        self.assertFalse(_denied(_gate("csop-gate-pathblock.py",
                         _bash("cat .cmk/x.mk"), env)))
        # a destructive shell verb on the subtree is denied
        self.assertTrue(_denied(_gate("csop-gate-pathblock.py",
                        _bash("rm -rf .cmk/vendored"), env)))
        # an exempt worktree copy is skipped
        self.assertFalse(_denied(_gate("csop-gate-pathblock.py",
                         _bash("rm -rf scratch/iso/mk/.cmk/vendored"), env)))
        # a relative op whose exempt fragment is only in the cwd is skipped
        in_tree = _bash("rm -rf .cmk/vendored")
        in_tree["cwd"] = "/repo/scratch/iso/mk"
        self.assertFalse(_denied(_gate("csop-gate-pathblock.py", in_tree, env)))
        # the fragment is not matched inside a longer filename
        self.assertFalse(_denied(_gate("csop-gate-pathblock.py",
                         _bash("rm -rf build/foo.cmk/out"), env)))

    def test_freeze_no_write_blocks_shell_verb(self):
        proj = _project({"freeze": {"default_enabled": True,
                         "frozen": ["build/artifact.js"]}})     # bare -> no-write default
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "freeze"], env)
        self.assertTrue(_denied(_gate("csop-gate-pathblock.py",
                        _bash("mv build/artifact.js /tmp/x"), env)))
        self.assertFalse(_denied(_gate("csop-gate-pathblock.py",
                         _bash("cat build/artifact.js"), env)))

    def test_destructive_verbs_substrate(self):
        self.assertEqual(csop.destructive_verbs("rm -rf a && mv b c"), ["mv", "rm"])
        self.assertEqual(csop.destructive_verbs("chmod +x alarm.sh"), [])
        self.assertEqual(csop.destructive_verbs(""), [])

    def test_techwrite_emdash(self):
        env = _env(); _cli(["enable", "techwrite"], env)
        bad = _edit(old="x", new="a " + EM_DASH + " b")
        ok = _edit(old="x", new="a, b")
        self.assertTrue(_denied(_gate("csop-gate-techwrite.py", bad, env)))
        self.assertFalse(_denied(_gate("csop-gate-techwrite.py", ok, env)))

    def test_techwrite_discouraged_warns_without_denying(self):
        env = _env(); _cli(["enable", "techwrite"], env)
        jargon = _edit(path="doc.md", old="x", new="the gate can leverage this")
        cp = _gate("csop-gate-techwrite.py", jargon, env)
        self.assertFalse(_denied(cp))
        self.assertIn(b"discouraged", cp.stdout)
        fenced = _edit(path="doc.md", old="x", new="a `gate` in a span")
        self.assertNotIn(b"discouraged", _gate("csop-gate-techwrite.py", fenced, env).stdout)
        code = _edit(path="a.py", old="x", new="the gate runs")
        self.assertNotIn(b"discouraged", _gate("csop-gate-techwrite.py", code, env).stdout)

    def test_techwrite_banned_tic_any_case(self):
        env = _env(); _cli(["enable", "techwrite"], env)
        tic = "load-" + "bearing"                # split so this source line stays clean
        bad = _edit(path="a.py", old="x", new="# a " + tic.upper() + " assumption")
        ok = _edit(path="a.py", old="x", new="# an assumption other code relies on")
        self.assertTrue(_denied(_gate("csop-gate-techwrite.py", bad, env)))
        self.assertFalse(_denied(_gate("csop-gate-techwrite.py", ok, env)))

    def test_techwrite_banned_phrase(self):
        env = _env(); _cli(["enable", "techwrite"], env)
        phrase = "earns its " + "keep"           # split so this source line is not itself flagged
        bad = _edit(old="x", new="this feature " + phrase + " here")
        ok = _edit(old="x", new="this feature is worth its cost here")
        self.assertTrue(_denied(_gate("csop-gate-techwrite.py", bad, env)))
        self.assertFalse(_denied(_gate("csop-gate-techwrite.py", ok, env)))

    def test_techwrite_prose_masking(self):
        env = _env(); _cli(["enable", "techwrite"], env)
        em = EM_DASH

        def w(body):
            return {"tool_name": "Write",
                    "tool_input": {"file_path": "doc.md", "content": body}}
        self.assertTrue(_denied(_gate("csop-gate-techwrite.py", w("a " + em + " b\n"), env)))
        self.assertFalse(_denied(_gate("csop-gate-techwrite.py",
                         w("```\na " + em + " b\n```\n"), env)))
        self.assertFalse(_denied(_gate("csop-gate-techwrite.py",
                         w("see `a " + em + " b` here\n"), env)))

    def test_techwrite_code_in_prose(self):
        proj = _project({"techwrite": {"default_enabled": True, "prose_rules": [
            {"pattern": "\\$\\(", "message": "shell/make expansion in prose"}]}})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "techwrite"], env)

        def w(body):
            return {"tool_name": "Write",
                    "tool_input": {"file_path": "doc.md", "content": body}}
        self.assertTrue(_denied(_gate("csop-gate-techwrite.py", w("run $(FOO) now\n"), env)))
        self.assertFalse(_denied(_gate("csop-gate-techwrite.py", w("run `$(FOO)` now\n"), env)))
        self.assertFalse(_denied(_gate("csop-gate-techwrite.py", w("```\n$(FOO)\n```\n"), env)))

    def test_techwrite_masks_html_and_tables(self):
        proj = _project({"techwrite": {"default_enabled": True, "prose_rules": [
            {"pattern": "\\$\\(", "message": "shell/make expansion in prose"}]}})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "techwrite"], env)

        def w(body):
            return {"tool_name": "Write",
                    "tool_input": {"file_path": "doc.md", "content": body}}
        self.assertFalse(_denied(_gate("csop-gate-techwrite.py",
                         w("before\n<pre>\n$(FOO)\n</pre>\nafter\n"), env)))     # html block
        self.assertFalse(_denied(_gate("csop-gate-techwrite.py",
                         w("a <code>$(FOO)</code> b\n"), env)))                  # inline html
        self.assertFalse(_denied(_gate("csop-gate-techwrite.py",
                         w("| col | val |\n| --- | --- |\n| x | $(FOO) |\n"), env)))  # md table
        self.assertTrue(_denied(_gate("csop-gate-techwrite.py",
                        w("plain $(FOO) leak\n"), env)))                         # still caught

    def test_techwrite_in_spans_token_exempt(self):
        proj = _project({"techwrite": {"default_enabled": True,
            "exempt": ["quickref.md.j2"], "prose_rules": [
                {"pattern": "\\$\\(", "message": "make expansion"},
                {"pattern": "(?<![\\w.])(?:self|this)\\.\\w",
                 "message": "bare anchor", "in_spans": True}]}})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "techwrite"], env)

        def w(path, body):
            return {"tool_name": "Write", "tool_input": {"file_path": path, "content": body}}
        # an in_spans rule catches self. even inside backticks
        self.assertTrue(_denied(_gate("csop-gate-techwrite.py",
                        w("doc.md", "see `self.foo` here\n"), env)))
        # a plain rule still passes inside backticks
        self.assertFalse(_denied(_gate("csop-gate-techwrite.py",
                         w("doc.md", "see `$(FOO)` here\n"), env)))
        # a per-line token opts the line out
        self.assertFalse(_denied(_gate("csop-gate-techwrite.py",
                         w("doc.md", "run $(FOO) now  docs-code-ok\n"), env)))
        # an exempt basename is skipped entirely
        self.assertFalse(_denied(_gate("csop-gate-techwrite.py",
                         w("docs/quickref.md.j2", "run $(FOO) now\n"), env)))

    def test_ftypes_reminder(self):
        proj = _project({"ftypes": {"default_enabled": True, "types": [
            {"match": ["*.sql"], "reminder": "use parameterized queries"}]}})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "ftypes"], env)
        cp = _gate("csop-react-ftypes.py",
                   {"tool_name": "Write", "tool_input": {"file_path": "q.sql",
                    "content": "select 1"}}, env)
        out = cp.stdout.decode()
        self.assertEqual(cp.returncode, 0)
        self.assertIn("parameterized queries", out)
        self.assertIn("additionalContext", out)      # output reaches the model

    def test_ftypes_reminder_file_token(self):
        proj = _project({"ftypes": {"default_enabled": True, "types": [
            {"match": ["*.md"], "reminder": "regenerate {file} now"}]}})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "ftypes"], env)
        cp = _gate("csop-react-ftypes.py",
                   {"tool_name": "Write", "tool_input": {"file_path": "docs/a.md",
                    "content": "x"}}, env)
        self.assertIn("regenerate docs/a.md now", cp.stdout.decode())

    def test_ftypes_command_output_visible(self):
        proj = _project({"ftypes": {"default_enabled": True, "types": [
            {"match": ["*.md"], "command": "echo linted {file}"}]}})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "ftypes"], env)
        cp = _gate("csop-react-ftypes.py",
                   {"tool_name": "Edit", "tool_input": {"file_path": "docs/readme.md",
                    "old_string": "a", "new_string": "b"}}, env)
        out = cp.stdout.decode()
        self.assertIn("additionalContext", out)
        self.assertIn("linted docs/readme.md", out)   # captured output plus {file} expansion

    def test_ftypes_no_match_and_inactive(self):
        cfg = {"ftypes": {"default_enabled": True, "types": [
            {"match": ["*.sql"], "reminder": "sql only"}]}}
        proj = _project(cfg)
        ev = {"tool_name": "Write", "tool_input": {"file_path": "x.py", "content": "p"}}
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "ftypes"], env)
        self.assertNotIn("additionalContext", _gate("csop-react-ftypes.py", ev, env).stdout.decode())
        env2 = _env(CLAUDE_PROJECT_DIR=proj)          # never enabled: fully inert
        sql = {"tool_name": "Write", "tool_input": {"file_path": "q.sql", "content": "s"}}
        self.assertNotIn("additionalContext", _gate("csop-react-ftypes.py", sql, env2).stdout.decode())

    def test_ftypes_malformed_entry_is_loud(self):
        proj = _project({"ftypes": {"default_enabled": True, "types": [
            {"match_globs": ["*.sql"], "reminder": "sql only"}]}})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "ftypes"], env)
        cp = _gate("csop-react-ftypes.py",
                   {"tool_name": "Write", "tool_input": {"file_path": "q.sql",
                    "content": "select 1"}}, env)
        out = cp.stdout.decode()
        self.assertIn("malformed", out)               # a bad key never silently no-matches
        self.assertIn("match_globs", out)             # the offending key is named

    def test_idiom_malformed_rule_is_loud(self):
        proj = _project({"idiom": {"default_enabled": True, "reject": [
            {"regex": "foo", "message": "no foo"}]}})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "idiom"], env)
        out = _gate("csop-gate-idiom.py",
                    _wr("a.py", "foo\n"), env).stdout.decode()
        self.assertIn("unusable config", out)
        self.assertIn("pattern", out)

    def test_techwrite_malformed_rule_is_loud(self):
        proj = _project({"techwrite": {"default_enabled": True, "prose_rules": [
            {"message": "code in prose"}]}})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "techwrite"], env)
        out = _gate("csop-gate-techwrite.py",
                    _wr("doc.md", "plain prose\n"), env).stdout.decode()
        self.assertIn("unusable config", out)

    def test_hyg_malformed_doc_region_is_loud(self):
        proj = _project({"hyg": {"default_enabled": True, "doc_regions": [
            {"begin": "'''", "end": "'''"}]}})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "hyg"], env)
        out = _gate("csop-gate-hyg.py", _wr("a.py", "x = 1\n"), env).stdout.decode()
        self.assertIn("unusable config", out)

    def test_freeze_malformed_entry_is_loud(self):
        proj = _project({"freeze": {"default_enabled": True, "frozen": [
            {"file": "vendor/", "why": "generated"}]}})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "freeze"], env)
        out = _gate("csop-gate-pathblock.py", _wr("a.py", "x = 1\n"), env).stdout.decode()
        self.assertIn("unusable config", out)
        self.assertIn("path", out)

    def test_wellformed_config_stays_quiet(self):
        proj = _project({"idiom": {"default_enabled": True, "reject": [
            {"pattern": "zzz", "message": "no zzz"}]}})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "idiom"], env)
        out = _gate("csop-gate-idiom.py", _wr("a.py", "fine\n"), env).stdout.decode()
        self.assertNotIn("unusable config", out)

    def test_racc_visible_edits(self):
        env = _env(); _cli(["enable", "racc"], env)
        self.assertTrue(_denied(_gate("csop-gate-racc.py", _bash("sed -i s/a/b/ f.py"), env)))
        self.assertTrue(_denied(_gate("csop-gate-racc.py", _bash("echo hi > f.py"), env)))
        self.assertTrue(_denied(_gate("csop-gate-racc.py", _bash("tee f.py < in"), env)))
        self.assertFalse(_denied(_gate("csop-gate-racc.py", _bash("cat f.py"), env)))
        self.assertFalse(_denied(_gate("csop-gate-racc.py", _bash("grep x f.py 2>/dev/null"), env)))

    def test_racc_shell_write_bypasses(self):
        env = _env(); _cli(["enable", "racc"], env)
        denied = ["cat >> tests/test_x.py <<'EOF'\nassert 1\nEOF",
                  "patch -p1 < fix.diff",
                  "g" + "it apply fix.diff",              # split: this repo's live hacc gate reads the source
                  "ed f.py",
                  "python3 -c \"open('f.py','a').write('x')\"",
                  "python3 - <<'EOF'\nopen('f.py','w').write('x')\nEOF"]
        allowed = ["pip install -U requests", "npm install", "cat patch.diff",
                   "python3 -c \"print(open('f.py').read())\"", "make check"]
        for cmd in denied:
            self.assertTrue(_denied(_gate("csop-gate-racc.py", _bash(cmd), env)), cmd)
        for cmd in allowed:
            self.assertFalse(_denied(_gate("csop-gate-racc.py", _bash(cmd), env)), cmd)

    def test_hyg_shout(self):
        env = _env(); _cli(["enable", "hyg"], env)
        shout = _edit(path="x.py", old="v = 1", new="v = 1\n# NEVER do this")
        plain = _edit(path="x.py", old="v = 1", new="v = 1\n# do not do this")
        envvar = _edit(path="x.py", old="v = 1", new="v = 1\n# NO_COLOR disables it")
        self.assertTrue(_denied(_gate("csop-gate-hyg.py", shout, env)))
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", plain, env)))
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", envvar, env)))

    def test_hyg_shout_ok_builtin_acronyms(self):
        env = _env(); _cli(["enable", "hyg"], env)
        for word in ("TCP", "UDP", "NTP", "DNS", "SSH"):
            edit = _edit(path="x.py", old="v = 1",
                         new="v = 1\n# uses {0} under the hood".format(word))
            self.assertFalse(_denied(_gate("csop-gate-hyg.py", edit, env)), word)

    def test_hyg_shout_ok_project_override_appends(self):
        proj = _project({"hyg": {"shout_ok": ["FOOBAR"]}})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "hyg"], env)
        added = _edit(path="x.py", old="v = 1", new="v = 1\n# FOOBAR is fine here")
        builtin = _edit(path="x.py", old="v = 1", new="v = 1\n# TCP is still fine")
        shout = _edit(path="x.py", old="v = 1", new="v = 1\n# NEVER do this")
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", added, env)))     # project addition
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", builtin, env)))  # built-in survives
        self.assertTrue(_denied(_gate("csop-gate-hyg.py", shout, env)))     # still shouts

    def test_hyg_comment_markers_need_a_space(self):
        env = _env(); _cli(["enable", "hyg"], env)
        case = ('case "$1" in\n  --help) usage ;;\n  --version) echo "$V" ;;\n'
                '  *) die "no: $1" ;;\nesac')
        deref = "int f(int *p) {\n  *p = 1;\n  *q = 2;\n  *r = 3;\n}"
        block = "/* head\n * body\n * more\n */"
        sql = "-- one\n-- two\n-- three"
        lisp = ";; one\n;; two\n;; three"
        arm = _edit(path="x.sh", old="v=1", new=case)
        ptr = _edit(path="x.c", old="v=1", new=deref)
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", arm, env)))    # case arms are code
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", ptr, env)))    # so is a deref
        for path, body in (("x.sql", sql), ("x.el", lisp)):
            edit = _edit(path=path, old="v=1", new=body)
            self.assertTrue(_denied(_gate("csop-gate-hyg.py", edit, env)))
        blk = _edit(path="x.c", old="v=1", new=block)      # a region: the doc budget, not 1
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", blk, env)))

    def test_hyg_shout_covers_docs_not_code(self):
        env = _env(); _cli(["enable", "hyg"], env)
        shout = lambda p, new: _edit(path=p, old="v = 1", new="v = 1\n" + new)
        for path, line in (("x.py", '"""this is REALLY important"""'),
                           ("x.c", "/* NEVER do this */"),
                           ("x.py", "## NEVER do this"),
                           ("x.py", "# NEVER do this")):
            self.assertTrue(_denied(_gate("csop-gate-hyg.py", shout(path, line), env)), line)
        for path, line in (("x.py", '"""this is really important"""'),
                           ("x.py", '"""escape hatch: CSOP_HYG=off"""'),
                           ("x.py", '"""returns JSON over HTTP"""'),
                           ("x.py", "FLAG = 2")):
            self.assertFalse(_denied(_gate("csop-gate-hyg.py", shout(path, line), env)), line)

    def test_hyg_doc_budget_is_by_marker_not_position(self):
        env = _env(); _cli(["enable", "hyg"], env)
        write = lambda path, body: {"tool_name": "Write",
                                    "tool_input": {"file_path": path, "content": body}}
        docmax = disciplines.GenerativeHygiene.doc_max_comment_lines
        lines = lambda n, pad="": "".join("{0}line {1}\n".format(pad, i) for i in range(n))
        # the same block passes or fails on its length alone, wherever it sits
        for pad, head, tail in (("", '"""\n', '"""\n'),
                                ("    ", 'def f():\n    """\n', '    """\n'),
                                ("", 'v = 1\n"""\n', '"""\n')):
            ok = head + lines(docmax, pad) + tail
            over = head + lines(docmax + 1, pad) + tail
            self.assertFalse(_denied(_gate("csop-gate-hyg.py", write("x.py", ok), env)), head)
            self.assertTrue(_denied(_gate("csop-gate-hyg.py", write("x.py", over), env)), head)
        # blank lines and bare delimiters are structure, so they cost nothing
        spaced = '"""\n' + "\n".join(lines(docmax).splitlines()) + '\n\n\n"""\n'
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", write("x.py", spaced), env)))

    def test_hyg_banner_separates_runs(self):
        env = _env(); _cli(["enable", "hyg"], env)
        write = lambda body: {"tool_name": "Write",
                              "tool_input": {"file_path": "x.py", "content": body}}
        banner = "# ---- section ----------------\n# a single note\nv = 1\n"
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", write(banner), env)))
        run = "# ---- section ----\n# note one\n# note two\nv = 1\n"
        self.assertTrue(_denied(_gate("csop-gate-hyg.py", write(run), env)))

    def test_hyg_block_cannot_be_grown_by_appends(self):
        env = _env(); _cli(["enable", "hyg"], env)
        docmax = disciplines.GenerativeHygiene.doc_max_comment_lines
        path = os.path.join(tempfile.mkdtemp(), "m.py")
        _write(path, '"""doc\nline 0\n"""\nv = 1\n')
        blocked_at = None
        for i in range(docmax + 10):
            old, new = "line {0}\n".format(i), "line {0}\nline {1}\n".format(i, i + 1)
            if _denied(_gate("csop-gate-hyg.py", _edit(path=path, old=old, new=new), env)):
                blocked_at = i
                break
            with open(path) as f:
                body = f.read()
            _write(path, body.replace(old, new, 1))
        self.assertIsNotNone(blocked_at, "a block grew past its budget one append at a time")
        self.assertLessEqual(blocked_at, docmax)
        over = '"""doc\n' + "".join("line {0}\n".format(i) for i in range(docmax + 5)) + '"""\n'
        _write(path, over)
        grow = _edit(path=path, old="line 3\n", new="line 3\nline 3b\n")
        cp = _gate("csop-gate-hyg.py", grow, env)
        self.assertTrue(_denied(cp))
        told = cp.stderr.decode()
        self.assertIn("grew a documentation block", told)   # not "added a 27-line block"
        self.assertIn("line 3b", told)                      # points at the added line
        # an over-budget block that is already there may still be edited or shrunk
        _write(path, '"""doc\n' + "".join("line {0}\n".format(i) for i in range(docmax + 5)) + '"""\n')
        touch = _edit(path=path, old="line 3\n", new="line three\n")
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", touch, env)))

    def test_hyg_prose_scope_is_configurable(self):
        block = "v = 1\n# one\n# two\n# three\n"
        write = lambda path: {"tool_name": "Write",
                              "tool_input": {"file_path": path, "content": block}}
        plain = _env(CLAUDE_PROJECT_DIR=_project({})); _cli(["enable", "hyg"], plain)
        self.assertTrue(_denied(_gate("csop-gate-hyg.py", write("x.py"), plain)))
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", write("x.mdx"), plain)))
        env = _env(CLAUDE_PROJECT_DIR=_project(
            {"hyg": {"prose_exts": ["vue"], "prose_dirs": ["handbook"]}}))
        _cli(["enable", "hyg"], env)
        for path in ("x.vue", "handbook/x.py", "x.md"):     # x.md: append kept the default
            self.assertFalse(_denied(_gate("csop-gate-hyg.py", write(path), env)), path)
        self.assertTrue(_denied(_gate("csop-gate-hyg.py", write("src/x.py"), env)))

    def test_repo_source_is_hygienic(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "hyggate", os.path.join(HOOKS, "csop-gate-hyg.py"))
        hyg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hyg)
        offenders = []
        for sub in ("hooks", "tools", "tests"):
            for name in sorted(os.listdir(os.path.join(ROOT, sub))):
                rel = os.path.join(sub, name)
                if not name.endswith(".py") or not hyg._in_scope(rel):
                    continue
                with open(os.path.join(ROOT, rel)) as f:
                    for finding in hyg._findings("", f.read(), markers=hyg._markers(rel)):
                        offenders.append("{0}: {1}".format(rel, finding[1]))
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_hyg_comment_markers_are_per_filetype(self):
        env = _env(); _cli(["enable", "hyg"], env)
        write = lambda path, body: {"tool_name": "Write",
                                    "tool_input": {"file_path": path, "content": body}}
        run = lambda marker: "{0} one\n{0} two\n{0} three\n".format(marker)
        # a marker is a comment only in a language that spells it that way
        for path, marker in (("a.py", "#"), ("a.js", "//"), ("a.go", "//"),
                             ("a.sql", "--"), ("a.el", ";"), ("Makefile", "#"),
                             ("a.unknown", "#")):
            self.assertTrue(_denied(_gate("csop-gate-hyg.py",
                            write(path, run(marker)), env)), path + " " + marker)
        for path, marker in (("a.py", "//"), ("a.js", "#"), ("a.css", "#"),
                             ("a.html", "#"), ("a.go", "#")):
            self.assertFalse(_denied(_gate("csop-gate-hyg.py",
                             write(path, run(marker)), env)), path + " " + marker)
        # css has no line comment at all, so selectors are code, braces and all
        css = "#header {\n  color: red;\n}\n#footer {\n  color: blue;\n}\n* {\n  margin: 0;\n}\n"
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", write("a.css", css), env)))
        stacked = "#header,\n#footer,\n#nav {\n  color: red;\n}\n"
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", write("a.css", stacked), env)))
        # its block comments are still documentation, and still budgeted
        long_block = "/*\n" + "".join(" * line {0}\n".format(i) for i in range(12)) + " */\n"
        self.assertTrue(_denied(_gate("csop-gate-hyg.py", write("a.css", long_block), env)))

    def test_hyg_markers_are_configurable(self):
        proj = _project({"hyg": {"comment_markers": {"css": ["#"]}}})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "hyg"], env)
        write = {"tool_name": "Write", "tool_input": {
            "file_path": "a.css", "content": "#one\n#two\n#three\n"}}
        self.assertTrue(_denied(_gate("csop-gate-hyg.py", write, env)))

    def test_hyg_banner_uses_the_file_type_marker(self):
        env = _env(); _cli(["enable", "hyg"], env)
        write = lambda path, body: {"tool_name": "Write",
                                    "tool_input": {"file_path": path, "content": body}}
        for path, marker in (("a.py", "#"), ("a.sql", "--"), ("a.el", ";"),
                             ("a.tex", "%"), ("a.js", "//")):
            banner = "{0} ==== section ====\n{0} a note\n".format(marker)
            self.assertFalse(_denied(_gate("csop-gate-hyg.py",
                             write(path, banner), env)), path)
            run = "{0} ==== section ====\n{0} one\n{0} two\n".format(marker)
            self.assertTrue(_denied(_gate("csop-gate-hyg.py",
                            write(path, run), env)), path)

    def test_techwrite_masks_indented_and_rst_code(self):
        env = _env(); _cli(["enable", "techwrite"], env)
        write = lambda path, body: {"tool_name": "Write",
                                    "tool_input": {"file_path": path, "content": body}}
        code = "x = 1 " + EM_DASH + " y"
        masked = [("a.md", "text\n\n```\n" + code + "\n```\n"),
                  ("a.md", "text\n\n    " + code + "\n"),
                  ("a.rst", "text::\n\n    " + code + "\n"),
                  ("a.rst", ".. code-block:: python\n\n    " + code + "\n"),
                  ("a.rst", "see ``" + code + "`` here\n")]
        for path, body in masked:
            self.assertFalse(_denied(_gate("csop-gate-techwrite.py",
                             write(path, body), env)), body[:30])
        prose = [("a.md", "this " + EM_DASH + " that\n"),
                 ("a.md", "- a list item " + EM_DASH + " still prose\n"),
                 ("a.rst", "this " + EM_DASH + " that\n")]
        for path, body in prose:
            self.assertTrue(_denied(_gate("csop-gate-techwrite.py",
                            write(path, body), env)), body[:30])

    def test_hyg_doc_regions_own_budget(self):
        env = _env(); _cli(["enable", "hyg"], env)
        docmax = disciplines.GenerativeHygiene.doc_max_comment_lines
        body = lambda n, mark="": "".join("{0}line {1}\n".format(mark, i) for i in range(n))
        cases = [
            ("x.py", '"""\n' + body(2) + '"""', '"""\n' + body(docmax + 2) + '"""'),
            ("x.c", "/*\n" + body(2, " * ") + "*/",
                    "/*\n" + body(docmax + 2, " * ") + "*/"),
            ("x.j2", "{% comment %}\n" + body(2) + "{% endcomment %}",
                     "{% comment %}\n" + body(docmax + 2) + "{% endcomment %}"),
            ("x.html", "<!--\n" + body(2) + "-->",
                       "<!--\n" + body(docmax + 2) + "-->"),
        ]
        for path, ok, over in cases:
            good = {"tool_name": "Write", "tool_input": {"file_path": path, "content": ok}}
            bad = {"tool_name": "Write", "tool_input": {"file_path": path, "content": over}}
            self.assertFalse(_denied(_gate("csop-gate-hyg.py", good, env)), path)  # within budget
            self.assertTrue(_denied(_gate("csop-gate-hyg.py", bad, env)), path)    # over budget

    def test_hyg_doc_region_open_gating(self):
        env = _env(); _cli(["enable", "hyg"], env)
        midline = {"tool_name": "Write", "tool_input": {"file_path": "x.py",
                   "content": "x = re.compile('\"\"\"|\\'\\'\\'')"}}
        quoted = {"tool_name": "Write", "tool_input": {"file_path": "x.py",
                  "content": '# example: """not a docstring"""'}}
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", midline, env)))  # no region opened
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", quoted, env)))   # a # line never opens one

    def test_hyg_doc_prefixes_exempt(self):
        env = _env(); _cli(["enable", "hyg"], env)
        block = ("## header one\n## header two\n## header three\n"
                 "## has foo(bar) in it too")
        edit = _edit(path="x.py", old="v = 1", new="v = 1\n" + block)
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", edit, env)))

    def test_hyg_doc_region_edit_uses_on_disk_replay(self):
        env = _env(); _cli(["enable", "hyg"], env)
        d = tempfile.mkdtemp()
        docmax = disciplines.GenerativeHygiene.doc_max_comment_lines
        block = os.path.join(d, "mod.c")
        seed = "".join(" * line {0}\n".format(i) for i in range(docmax - 1))
        _write(block, "int f(void) {\n/*\n" + seed + " */\n}\n")
        last = " * line {0}\n".format(docmax - 2)
        grow = lambda tail: _edit(path=block, old=last + " */",
                                  new=last + tail + " */")
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", grow(" * one more\n"), env)))
        self.assertTrue(_denied(_gate("csop-gate-hyg.py",
                                      grow(" * one more\n * and another\n"), env)))

    def test_selfprotect_consumer_vs_source(self):
        hookfile = os.path.join(ROOT, "hooks", "csop-gate-hyg.py")
        edit = {"tool_name": "Edit", "tool_input": {"file_path": hookfile,
                "old_string": "x", "new_string": "y"}}
        consumer = _env(CLAUDE_PROJECT_DIR=tempfile.mkdtemp())
        self.assertTrue(_denied(_gate("csop-gate-selfprotect.py", edit, consumer)))  # vendored copy
        source = _env(CLAUDE_PROJECT_DIR=ROOT)
        self.assertFalse(_denied(_gate("csop-gate-selfprotect.py", edit, source)))   # plugin's own repo
        other = {"tool_name": "Write", "tool_input": {"file_path": "/tmp/x.py", "content": "z"}}
        self.assertFalse(_denied(_gate("csop-gate-selfprotect.py", other, consumer)))  # non-plugin file
        esc = _env(CLAUDE_PROJECT_DIR=tempfile.mkdtemp(), CSOP_SELFPROTECT="off")
        self.assertFalse(_denied(_gate("csop-gate-selfprotect.py", edit, esc)))       # escape hatch

    def test_idiom_array_nudges(self):
        env = _env(); _cli(["enable", "idiom"], env)
        out = _gate("csop-nudge.py", {}, env).stdout.decode()
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(ctx.count("\n- "), 4)               # each array item is its own line
        self.assertIn("- Match the surrounding code", ctx)
        self.assertIn("- Prefer the language", ctx)

    def test_idiom_reject(self):
        proj = _project({"idiom": {"default_enabled": True, "action": "deny",
                         "reject": [{"pattern": "\\bvar\\b", "message": "use let/const"}]}})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "idiom"], env)
        bad = _edit(old="x", new="var y = 1")
        ok = _edit(old="x", new="const y = 1")
        self.assertTrue(_denied(_gate("csop-gate-idiom.py", bad, env)))
        self.assertFalse(_denied(_gate("csop-gate-idiom.py", ok, env)))
        env2 = _env(); _cli(["enable", "idiom"], env2)          # no reject rules, so inert
        self.assertFalse(_denied(_gate("csop-gate-idiom.py", bad, env2)))

    def test_hyg_region_state_from_relative_path(self):
        body = "/*\n * one\n */\nint x;\n"
        proj = _project({}, {"a.c": body})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "hyg"], env)
        edit = lambda p: _edit(path=p, old=" * one", new=" * one\n * two")
        for path in ("a.c", os.path.join(proj, "a.c")):
            self.assertFalse(_denied(_gate("csop-gate-hyg.py", edit(path), env)), path)
        unknown = _edit(path="gone.c", old=" * one", new=" * one\n * two")
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", unknown, env)))
        plain = _edit(path="gone.py", old="v = 1", new="v = 1\n# a\n# b\n# c")
        self.assertTrue(_denied(_gate("csop-gate-hyg.py", plain, env)))

    def test_hyg_enforced_in_iso_tree(self):
        env = _env(); _cli(["enable", "hyg"], env)
        block = "v = 1\n# a\n# b\n# c"                        # a 3-line comment block
        iso = _edit(path="scratch/iso/mk/x.py", old="v = 1", new=block)
        notes = _edit(path="scratch/notes/x.py", old="v = 1", new=block)
        self.assertTrue(_denied(_gate("csop-gate-hyg.py", iso, env)))     # iso: code for core, enforced
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", notes, env)))  # non-iso scratch: out of scope

    def test_groom_conflict_cascade(self):
        env = _env()
        _cli(["enable", "science"], env)                 # science requires iso
        _cli(["enable", "groom"], env)                   # groom conflicts iso
        active = _cli(["list"], env).stdout.decode()
        self.assertIn("groom", active)
        self.assertNotIn("iso", active)
        self.assertNotIn("science", active)              # cascade: science required iso
        stop = {"hook_event_name": "Stop"}
        first = _gate("csop-modeline.py", stop, env).stdout.decode()
        second = _gate("csop-modeline.py", stop, env).stdout.decode()
        self.assertIn("disabled", first)                 # one-time notice
        self.assertNotIn("disabled", second)             # drained after one show

    def test_disarm_blocks_every_agent_route(self):
        env = _env(); _cli(["enable", "iso"], env)
        cli = os.path.join(HOOKS, "csop.py")
        state = os.path.join(env["CLAUDE_PLUGIN_DATA"], "active.json")
        for cmd in ('python3 %s disable iso && echo ok' % cli,         # chained: not canonical
                    'python3 %s reset' % cli,
                    'CLAUDE_PLUGIN_DATA=/tmp/x python3 %s list' % cli,
                    'echo [] > %s' % state,
                    'rm %s' % state,
                    'python3 %s enable groom' % cli):                  # groom conflicts iso
            with self.subTest(cmd=cmd):
                cp = _gate("csop-gate-disarm.py", _bash(cmd), env)
                self.assertEqual(cp.returncode, 2, cp.stdout + cp.stderr)
        cp = _gate("csop-gate-disarm.py", _edit(state), env)
        self.assertEqual(cp.returncode, 2)

    def test_disarm_escalates_the_slash_command_form_to_the_human(self):
        env = _env(); _cli(["enable", "iso"], env)
        cli = os.path.join(HOOKS, "csop.py")
        for cmd in ('python3 "%s" disable iso' % cli,    # the command body, quoted
                    "python3 %s disable all" % cli):
            with self.subTest(cmd=cmd):
                cp = _gate("csop-gate-disarm.py", _bash(cmd), env)
                self.assertEqual(cp.returncode, 0)
                self.assertIn('"ask"', cp.stdout.decode())   # sign-off, not a free pass

    def test_disarm_ignores_everything_else(self):
        env = _env()
        for cmd in ("python3 %s list" % os.path.join(HOOKS, "csop.py"),
                    "grep -rn disable hooks/", "make test"):
            with self.subTest(cmd=cmd):
                cp = _gate("csop-gate-disarm.py", _bash(cmd), env)
                self.assertEqual(cp.returncode, 0, cp.stderr)
                self.assertNotIn('"ask"', cp.stdout.decode())

    def test_disarm_is_always_on_with_no_escape_hatch(self):
        env = _env(CSOP_DISARM="off"); _cli(["enable", "iso"], env)
        cmd = "python3 %s reset" % os.path.join(HOOKS, "csop.py")
        self.assertEqual(_gate("csop-gate-disarm.py", _bash(cmd), env).returncode, 2)


class StageChecks(unittest.TestCase):
    def _proj(self):
        return _project({"stages": {
            "demo":   {"default_stage": True, "globs": ["demos/**"],
                       "disciplines": {"hyg": "off"}},
            "module": {"globs": ["src/**"], "from": ["demo"],
                       "disciplines": {"hyg": {"action": "nudge"}}},
            "core":   {"globs": ["core.py"], "from": ["module"],
                       "pre": {"text": "core change", "action": "deny"},
                       "post": "run the suite for {file}"}}})

    def _w(self, path):
        return {"tool_name": "Write", "tool_input": {"file_path": path, "content": "x"}}

    def test_stage_cli_and_unknown(self):
        env = _env(CLAUDE_PROJECT_DIR=self._proj())
        out = _cli(["stage"], env).stdout.decode()
        self.assertIn("(none)", out)
        self.assertIn("available:", out)                # lists defined stages per config
        for s in ("demo", "module", "core"):
            self.assertIn(s, out)
        _cli(["stage", "module"], env)
        self.assertIn("stage: module", _cli(["stage"], env).stdout.decode())
        self.assertEqual(_cli(["stage", "bogus"], env).returncode, 2)

    def test_promote_climbs_ladder(self):
        env = _env(CLAUDE_PROJECT_DIR=self._proj()); _cli(["stage", "demo"], env)
        self.assertIn("demo -> module", _cli(["promote"], env).stdout.decode())
        self.assertIn("stage: module", _cli(["stage"], env).stdout.decode())
        self.assertIn("module -> core", _cli(["promote"], env).stdout.decode())
        self.assertIn("top", _cli(["promote"], env).stdout.decode())          # core has no successor

    def test_promote_emits_new_nudges(self):
        proj = _project({"stages": {
            "spike": {"default_stage": True, "globs": ["scratch/**"]},
            "core": {"globs": ["src/**"], "from": ["spike"], "disciplines": {"tdd": {}}}}})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "pro"], env)
        _cli(["stage", "spike"], env)
        out = _cli(["promote"], env).stdout.decode()
        self.assertIn("promoted: spike -> core", out)
        self.assertIn("failing test first", out)          # tdd nudge, freshly activated by core
        # a stage that activates nothing emits only the transition line
        proj2 = _project({"stages": {
            "spike": {"default_stage": True, "globs": ["scratch/**"]},
            "core": {"globs": ["src/**"], "from": ["spike"]}}})
        env2 = _env(CLAUDE_PROJECT_DIR=proj2); _cli(["enable", "pro"], env2)
        _cli(["stage", "spike"], env2)
        out2 = _cli(["promote"], env2).stdout.decode()
        self.assertNotIn("- ", out2)

    def test_demote_walks_down(self):
        env = _env(CLAUDE_PROJECT_DIR=self._proj()); _cli(["stage", "core"], env)
        self.assertIn("demoted: core -> module", _cli(["demote"], env).stdout.decode())
        self.assertIn("demoted: module -> demo", _cli(["demote"], env).stdout.decode())
        self.assertIn("bottom", _cli(["demote"], env).stdout.decode())        # demo is a root
        env2 = _env(CLAUDE_PROJECT_DIR=self._proj())                          # no current stage
        self.assertEqual(_cli(["demote"], env2).returncode, 2)

    def test_demote_explicit_and_invalid(self):
        env = _env(CLAUDE_PROJECT_DIR=self._proj()); _cli(["stage", "core"], env)
        self.assertIn("demoted: core -> module", _cli(["demote", "module"], env).stdout.decode())
        env2 = _env(CLAUDE_PROJECT_DIR=self._proj()); _cli(["stage", "core"], env2)
        self.assertEqual(_cli(["demote", "demo"], env2).returncode, 2)        # demo not a source of core

    def test_promote_explicit_and_invalid(self):
        env = _env(CLAUDE_PROJECT_DIR=self._proj()); _cli(["stage", "demo"], env)
        self.assertIn("demo -> module", _cli(["promote", "module"], env).stdout.decode())
        env2 = _env(CLAUDE_PROJECT_DIR=self._proj()); _cli(["stage", "demo"], env2)
        self.assertEqual(_cli(["promote", "core"], env2).returncode, 2)       # core not a successor of demo

    def test_promote_ambiguous_and_no_stage(self):
        proj = _project({"stages": {"demo": {"default_stage": True, "globs": ["d/**"]},
                         "a": {"globs": ["a/**"], "from": ["demo"]},
                         "b": {"globs": ["b/**"], "from": ["demo"]}}})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["stage", "demo"], env)
        self.assertIn("ambiguous", _cli(["promote"], env).stdout.decode())
        self.assertIn("stage: demo", _cli(["stage"], env).stdout.decode())    # unchanged
        env2 = _env(CLAUDE_PROJECT_DIR=proj)                                  # no current stage
        self.assertEqual(_cli(["promote"], env2).returncode, 2)

    def test_stage_seed_on_reset(self):
        env = _env(CLAUDE_PROJECT_DIR=self._proj())
        _gate("csop-session-reset.py", {"source": "startup"}, env)
        self.assertIn("stage: demo", _cli(["stage"], env).stdout.decode())

    def test_stage_discipline_override(self):
        env = _env(CLAUDE_PROJECT_DIR=self._proj()); _cli(["enable", "hyg"], env)
        bad = _edit(path="x.py", old="v = 1", new="v = 1\n# NEVER do this")
        _cli(["stage", "demo"], env)
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", bad, env)))   # hyg off in demo
        _cli(["stage", "core"], env)
        self.assertTrue(_denied(_gate("csop-gate-hyg.py", bad, env)))    # core: session hyg applies

    def test_stage_downgrade_action(self):
        env = _env(CLAUDE_PROJECT_DIR=self._proj()); _cli(["enable", "hyg"], env)
        bad = _edit(path="x.py", old="v = 1", new="v = 1\n# NEVER do this")
        _cli(["stage", "module"], env)                                   # hyg block -> nudge
        cp = _gate("csop-gate-hyg.py", bad, env)
        self.assertFalse(_denied(cp))
        self.assertIn("additionalContext", cp.stdout.decode())

    def test_promotion_pre_origination_vs_promoted(self):
        env = _env(CLAUDE_PROJECT_DIR=self._proj()); _cli(["enable", "pro"], env)
        _cli(["stage", "core"], env)                                     # no module in history
        self.assertTrue(_denied(_gate("csop-gate-promotion.py", self._w("core.py"), env)))
        env2 = _env(CLAUDE_PROJECT_DIR=self._proj()); _cli(["enable", "pro"], env2)
        _cli(["stage", "module"], env2); _cli(["stage", "core"], env2)   # arrived via module
        self.assertFalse(_denied(_gate("csop-gate-promotion.py", self._w("core.py"), env2)))

    def test_promotion_pre_root_and_once(self):
        env = _env(CLAUDE_PROJECT_DIR=self._proj()); _cli(["enable", "pro"], env)
        _cli(["stage", "demo"], env)
        self.assertFalse(_denied(_gate("csop-gate-promotion.py", self._w("demos/x"), env)))  # root
        _cli(["stage", "core"], env)
        self.assertTrue(_denied(_gate("csop-gate-promotion.py", self._w("core.py"), env)))   # first
        self.assertFalse(_denied(_gate("csop-gate-promotion.py", self._w("core.py"), env)))  # once/session

    def test_promotion_post(self):
        env = _env(CLAUDE_PROJECT_DIR=self._proj()); _cli(["enable", "pro"], env)
        _cli(["stage", "core"], env)
        ev = {"hook_event_name": "PostToolUse", "tool_name": "Write",
              "tool_input": {"file_path": "core.py", "content": "x"}}
        out = _gate("csop-gate-promotion.py", ev, env).stdout.decode()
        self.assertIn("additionalContext", out)
        self.assertIn("run the suite for core.py", out)

    def test_modeline_stage_element(self):
        env = _env(CLAUDE_PROJECT_DIR=self._proj())
        _cli(["enable", "pro"], env); _cli(["stage", "module"], env)
        out = _gate("csop-modeline.py", {"hook_event_name": "Stop"}, env).stdout.decode()
        self.assertIn("Stage", out)
        self.assertIn("module", out)

    def test_writable_denies_ahead_of_stage(self):
        env = _env(CLAUDE_PROJECT_DIR=self._proj()); _cli(["enable", "pro"], env)
        _cli(["stage", "demo"], env)
        self.assertTrue(_denied(_gate("csop-gate-promotion.py",
                        self._w("src/foo.mk"), env)))            # module file, outside writable(demo)
        self.assertFalse(_denied(_gate("csop-gate-promotion.py",
                         self._w("demos/x"), env)))              # in writable(demo)
        self.assertFalse(_denied(_gate("csop-gate-promotion.py",
                         self._w("README.md"), env)))            # unclassified: passes

    def test_writable_allows_after_promotion(self):
        env = _env(CLAUDE_PROJECT_DIR=self._proj()); _cli(["enable", "pro"], env)
        _cli(["stage", "demo"], env); _cli(["stage", "module"], env)
        self.assertFalse(_denied(_gate("csop-gate-promotion.py",
                         self._w("src/foo.mk"), env)))           # writable(module) includes src/**

    def test_effective_config_merge(self):
        proj = _project({"stages": {"demo": {"default_stage": True, "globs": ["demos/**"],
                         "disciplines": {"hyg": {"max_comment_lines": 5}}}}})
        body = "x = 1\n# a\n# b\n# c\n"                       # a 3-line comment block
        w = {"tool_name": "Write", "tool_input": {"file_path": "x.py", "content": body}}
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "hyg"], env)
        _cli(["stage", "demo"], env)
        self.assertFalse(_denied(_gate("csop-gate-hyg.py", w, env)))   # stage raised max to 5
        env2 = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "hyg"], env2)   # no current stage
        self.assertTrue(_denied(_gate("csop-gate-hyg.py", w, env2)))   # default max 1 -> blocked

    def test_effective_active_on_off(self):
        proj = _project({"stages": {
            "demo": {"default_stage": True, "globs": ["demos/**"],
                     "disciplines": {"hyg": "off", "tdd": "on"}}}})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "hyg"], env)
        _cli(["stage", "demo"], env)
        # nudge (pre-turn) reflects the effective set: tdd on appears, hyg off is gone
        out = _gate("csop-nudge.py", {}, env).stdout.decode()
        self.assertIn("Test-Driven", out)          # stage `on` gateless discipline is nudged
        self.assertNotIn("Generative Hygiene", out)  # stage `off` discipline is not
        # modeline Disciplines list agrees
        ml = _gate("csop-modeline.py", {"hook_event_name": "Stop"}, env).stdout.decode()
        self.assertIn("tdd", ml)
        self.assertNotIn("hyg", ml)

    def test_writable_explicit_override(self):
        proj = _project({"stages": {
            "lab":  {"default_stage": True, "globs": ["lab/**"],
                     "writable": ["lab/**", "shared/**"]},
            "core": {"globs": ["core.py"], "from": ["lab"]}}})
        env = _env(CLAUDE_PROJECT_DIR=proj); _cli(["enable", "pro"], env)
        _cli(["stage", "lab"], env)
        self.assertFalse(_denied(_gate("csop-gate-promotion.py",
                         self._w("shared/x"), env)))             # explicit writable
        self.assertFalse(_denied(_gate("csop-gate-promotion.py",
                         self._w("other/y"), env)))              # unclassified: passes
        self.assertTrue(_denied(_gate("csop-gate-promotion.py",
                        self._w("core.py"), env)))               # core file, outside writable(lab)


class InstallChecks(unittest.TestCase):
    def test_version_check_falls_back_to_claude_code_execpath(self):
        stub_dir = tempfile.mkdtemp()
        stub = os.path.join(stub_dir, "claude-stub")
        _write(stub, "#!/bin/sh\necho '99.0.0 (Claude Code)'\n")
        os.chmod(stub, 0o755)
        env = dict(os.environ)
        env.pop("SKIP_VERSION_CHECK", None)
        env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin"  # no 'claude' here
        env["CLAUDE_CODE_EXECPATH"] = stub
        env["CLAUDE_CODE_ENTRYPOINT"] = "claude-desktop"
        r = subprocess.run(["make", "version-check", "NO_COLOR=1"],
                            cwd=ROOT, capture_output=True, env=env)
        out = r.stdout.decode() + r.stderr.decode()
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("CLAUDE_CODE_EXECPATH", out)
        self.assertIn("99.0.0", out)

    def test_install_prunes_stale_and_no_dead_paths(self):
        client = tempfile.mkdtemp()
        os.makedirs(os.path.join(client, ".claude"))
        rel = os.path.relpath(os.path.realpath(ROOT), os.path.realpath(client))
        stale = 'python3 "${CLAUDE_PROJECT_DIR}/%s/hooks/reminder.py"' % rel
        theirs = "echo their-own-hook"
        _write(os.path.join(client, ".claude", "settings.json"), json.dumps({"hooks": {
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": stale}]}],
            "PreToolUse": [{"matcher": "Bash",
                            "hooks": [{"type": "command", "command": theirs}]}]}}))
        subprocess.run(["make", "install", "DEST=" + client, "NO_COLOR=1",
                        "SKIP_VERSION_CHECK=1"], cwd=ROOT, capture_output=True)
        with open(os.path.join(client, ".claude", "settings.json")) as f:
            cfg = json.load(f)
        cmds = [h["command"] for gs in cfg["hooks"].values() for g in gs
                for h in g["hooks"]]
        self.assertNotIn(stale, cmds)                          # stale reminder.py pruned
        self.assertTrue(any("nudge.py" in c for c in cmds))    # current hook wired
        self.assertIn(theirs, cmds)                            # consumer's own hook kept
        self.assertTrue(any('csop.py" *)' in a for a in cfg["permissions"]["allow"]))
        self.assertTrue(all("${CLAUDE_PROJECT_DIR}" in a for a in cfg["permissions"]["allow"]))
        for c in cmds:                                         # every csop hook path is real
            m = re.search(r"\$\{CLAUDE_PROJECT_DIR\}/(\S+\.py)", c)
            if m:
                self.assertTrue(os.path.isfile(os.path.join(client, m.group(1))),
                                "dead hook path: " + c)

    def test_install_survives_symlinked_client_dir(self):
        real_client = tempfile.mkdtemp()
        link_dir = tempfile.mkdtemp()
        client = os.path.join(link_dir, "client-link")
        os.symlink(real_client, client)
        os.makedirs(os.path.join(client, ".claude"))
        subprocess.run(["make", "install", "DEST=" + client, "NO_COLOR=1",
                        "SKIP_VERSION_CHECK=1"], cwd=ROOT, capture_output=True)
        with open(os.path.join(client, ".claude", "settings.json")) as f:
            cfg = json.load(f)
        cmds = [h["command"] for gs in cfg["hooks"].values() for g in gs
                for h in g["hooks"]]
        for c in cmds:
            m = re.search(r"\$\{CLAUDE_PROJECT_DIR\}/(\S+\.py)", c)
            if m:
                self.assertTrue(os.path.isfile(os.path.join(client, m.group(1))),
                                "dead hook path via symlinked client: " + c)


class SyncCommandsChecks(unittest.TestCase):
    """Pruning deletes files in a consumer's repo, so each guard gets a test."""

    def _dirs(self):
        src = tempfile.mkdtemp()
        dest = os.path.join(tempfile.mkdtemp(), ".claude", "commands")
        os.makedirs(dest)
        _write(os.path.join(src, "sop.md"), _CMD % "")
        return src, dest

    def test_writes_commands_with_plugin_root_rewritten(self):
        src, dest = self._dirs()
        sync_commands.sync(src, dest, "tools/csop")
        with open(os.path.join(dest, "sop.md")) as f:
            body = f.read()
        self.assertIn("${CLAUDE_PROJECT_DIR}/tools/csop/hooks/csop.py", body)
        self.assertNotIn("CLAUDE_PLUGIN_ROOT", body)

    def test_self_host_rel_has_no_dot_segment(self):
        src, dest = self._dirs()
        sync_commands.sync(src, dest, ".")
        with open(os.path.join(dest, "sop.md")) as f:
            self.assertIn("${CLAUDE_PROJECT_DIR}/hooks/csop.py", f.read())

    def test_prunes_a_retired_csop_command(self):
        src, dest = self._dirs()
        retired = os.path.join(dest, "disc.md")
        _write(retired, _CMD % "")
        log, (_, pruned, skipped) = sync_commands.sync(src, dest, "x")
        self.assertFalse(os.path.exists(retired))
        self.assertEqual((pruned, skipped), (1, 0))
        self.assertTrue(any("pruned" in ln and "disc.md" in ln for ln in log))

    def test_keeps_a_command_that_is_not_ours(self):
        src, dest = self._dirs()
        theirs = os.path.join(dest, "deploy.md")
        _write(theirs, "---\ndescription: ours\n---\n!`make deploy`\n")
        log, (_, pruned, skipped) = sync_commands.sync(src, dest, "x")
        self.assertTrue(os.path.exists(theirs))
        self.assertEqual((pruned, skipped), (0, 1))
        self.assertTrue(any("kept" in ln and "deploy.md" in ln for ln in log))

    def test_keeps_a_command_merely_mentioning_csop(self):
        src, dest = self._dirs()
        near = os.path.join(dest, "notes.md")
        _write(near, "---\ndescription: how our hooks/csop.py works\n---\n!`ls`\n")
        sync_commands.sync(src, dest, "x")
        self.assertTrue(os.path.exists(near))

    def test_keeps_a_symlink_and_a_non_markdown_file(self):
        src, dest = self._dirs()
        target = os.path.join(tempfile.mkdtemp(), "real.md")
        _write(target, _CMD % "")
        link = os.path.join(dest, "linked.md")
        os.symlink(target, link)
        other = os.path.join(dest, "README.txt")
        _write(other, "not a command")
        sync_commands.sync(src, dest, "x")
        self.assertTrue(os.path.islink(link))
        self.assertTrue(os.path.isfile(target))
        self.assertTrue(os.path.isfile(other))

    def test_dry_run_changes_nothing(self):
        src, dest = self._dirs()
        retired = os.path.join(dest, "disc.md")
        _write(retired, _CMD % "")
        log, (_, pruned, _s) = sync_commands.sync(src, dest, "x", dry_run=True)
        self.assertTrue(os.path.exists(retired))
        self.assertFalse(os.path.exists(os.path.join(dest, "sop.md")))
        self.assertEqual(pruned, 1)
        self.assertTrue(any("would prune" in ln for ln in log))

    def test_refuses_a_destination_outside_a_claude_commands_dir(self):
        src, _d = self._dirs()
        victim = tempfile.mkdtemp()
        _write(os.path.join(victim, "keep.md"), "important")
        with self.assertRaises(ValueError):
            sync_commands.sync(src, victim, "x")
        self.assertTrue(os.path.isfile(os.path.join(victim, "keep.md")))

    def test_refuses_an_empty_source_so_a_bad_path_cannot_prune_everything(self):
        _s, dest = self._dirs()
        existing = os.path.join(dest, "sop.md")
        _write(existing, _CMD % "")
        with self.assertRaises(ValueError):
            sync_commands.sync(tempfile.mkdtemp(), dest, "x")
        self.assertTrue(os.path.isfile(existing))

    def test_sibling_update_rewires_each_client(self):
        """A pull alone leaves a client's settings.json pointing at the previous
        release's hooks, so the bulk updater has to re-run install per project."""
        with open(os.path.join(ROOT, "Makefile")) as f:
            recipe = f.read().split("update.siblings:")[1].split("\nclean:")[0]
        self.assertIn("install", recipe)
        self.assertIn("git -C", recipe)

    def test_sibling_update_resets_rather_than_pulls(self):
        """A vendored checkout is a pinned mirror, and upstream squashes, so the
        sweep has to survive a rewritten history that no pull can reconcile."""
        with open(os.path.join(ROOT, "Makefile")) as f:
            recipe = f.read().split("update.siblings:")[1].split("\nclean:")[0]
        self.assertIn("reset --hard", recipe)
        self.assertNotIn("git -C \"$$d\" pull", recipe)
        self.assertIn("status --porcelain", recipe)   # local edits stop the reset

    def test_install_prunes_a_retired_command_in_a_client(self):
        client = tempfile.mkdtemp()
        cmds = os.path.join(client, ".claude", "commands")
        os.makedirs(cmds)
        retired = os.path.join(cmds, "discipline.md")
        _write(retired, _CMD % "")
        theirs = os.path.join(cmds, "deploy.md")
        _write(theirs, "---\ndescription: theirs\n---\n!`make deploy`\n")
        r = subprocess.run(["make", "install", "DEST=" + client, "NO_COLOR=1",
                            "SKIP_VERSION_CHECK=1"], cwd=ROOT, capture_output=True)
        out = r.stdout.decode() + r.stderr.decode()
        self.assertFalse(os.path.exists(retired), out)
        self.assertTrue(os.path.isfile(theirs), out)
        self.assertTrue(os.path.isfile(os.path.join(cmds, "sop.md")), out)
        self.assertIn("discipline.md", out)   # the removal is logged for the human
        self.assertIn("deploy.md", out)       # so is the file left alone


if __name__ == "__main__":
    unittest.main()
