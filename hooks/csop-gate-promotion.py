#!/usr/bin/env python3
"""Promotion gate (codename `pro`): staged-flow prompts.

Fires on the edit tools, Pre and Post, when `pro` is active with a current stage.
Pre fires the stage's `pre` prompt once per session when no `from` source has
been current, and denies an edit outside the stage's writable set; Post feeds
back the stage's `post` note. Fail-open; escape hatch CSOP_PRO=off.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402

DISCIPLINE = disciplines.Promotion.codename
_WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


def main():
    event = csop.load_event()
    if event.get("tool_name") not in _WRITE_TOOLS:
        csop.allow()
    if not csop.is_active(DISCIPLINE) or csop.escaped(DISCIPLINE):
        csop.allow()
    cs = csop.current_stage()
    if not cs:
        csop.allow()
    cfg = csop.stages_config().get(cs) or {}
    ti = event.get("tool_input", {}) or {}
    fp = ti.get("file_path", "") or ti.get("notebook_path", "") or ""

    if event.get("hook_event_name") == "PostToolUse":
        post = cfg.get("post")
        if isinstance(post, str) and post:
            csop.nudge("Promotion ({0}) [{1}]: {2}".format(
                DISCIPLINE, cs, post.replace("{file}", fp)), "PostToolUse")
        csop.allow()

    if csop.writable_verdict(fp) == "deny":    # spatial guard: editing ahead of the stage
        fs = csop.stage_of(fp)
        csop.deny("Promotion ({0}) [{1}]: `{2}` belongs to stage `{3}`, outside "
                  "what `{1}` may write. Switch with `/csop stage {3}` (promoting "
                  "from its sources), or edit within `{1}`. Escape hatch: "
                  "CSOP_PRO=off.".format(DISCIPLINE, cs, fp, fs))

    froms = cfg.get("from") or []
    if not froms:
        csop.allow()                          # entry stage: origination is expected
    if any(s in csop.stage_history() for s in froms):
        csop.allow()                          # arrived via a valid source
    pre = cfg.get("pre") or {}
    text = pre.get("text") if isinstance(pre, dict) else pre
    if not text or csop.stage_pre_fired(cs):
        csop.allow()
    csop.mark_stage_pre(cs)
    action = pre.get("action") if isinstance(pre, dict) else "nudge"
    csop.enforce(action or "nudge",
                 "Promotion ({0}) [{1}]: {2}\nLegal sources: {3}. Escape hatch: "
                 "CSOP_PRO=off.".format(DISCIPLINE, cs, text.replace("{file}", fp),
                                        ", ".join(froms)))


if __name__ == "__main__":
    main()
