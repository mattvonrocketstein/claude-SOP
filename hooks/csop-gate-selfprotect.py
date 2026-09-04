#!/usr/bin/env python3
"""PreToolUse gate: CSOP protects its own hook files in consumer projects.

CSOP's hook code is read-only wherever the plugin is a vendored dependency, so a
write under its `hooks/` dir is denied: change it upstream and update the
submodule. The test is structural and this rail is always on, unlike the
toggleable disciplines. See docs/gate-internals.md. Hatch CSOP_SELFPROTECT=off.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402

_HOOKS = os.path.dirname(os.path.abspath(__file__))          # <plugin>/hooks
_PLUGIN = os.path.dirname(_HOOKS)                            # <plugin>
_WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


def _under(path, root):
    try:
        root = os.path.realpath(root)
        return os.path.commonpath([os.path.realpath(path), root]) == root
    except Exception:
        return False


def main():
    event = csop.load_event()
    if event.get("tool_name") not in _WRITE_TOOLS:
        csop.allow()
    if csop.escaped("selfprotect"):
        csop.allow()
    proj = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    if os.path.realpath(_PLUGIN) == os.path.realpath(proj):
        csop.allow()                          # the plugin's own repo: normal development
    ti = event.get("tool_input", {}) or {}
    fp = ti.get("file_path", "") or ti.get("notebook_path", "") or ""
    if not fp or not _under(fp, _HOOKS):
        csop.allow()
    csop.deny("CSOP self-protection: `{0}` is a CSOP plugin hook, read-only (no "
              "edits, no new files) in a consumer project. Change it upstream in the "
              "claude-SOP repo and update "
              "the submodule; do not edit the vendored copy. Escape hatch: "
              "CSOP_SELFPROTECT=off.".format(fp))


if __name__ == "__main__":
    main()
