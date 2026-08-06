#!/usr/bin/env python3
"""Merge CSOP's hooks and permissions into a consumer's .claude/settings.json.

Syncs rather than appends, so re-running is safe: it drops hook entries pointing
into our hooks dir, adds the current set, and unions the permissions that
pre-approve the /csop CLI. The consumer's own settings are preserved.
Usage: merge_settings.py <settings.json> <rel-path-to-plugin> <our-hooks.json>
"""
import json
import sys


def _rewrite(obj, rel):
    if isinstance(obj, dict):
        return {k: _rewrite(v, rel) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_rewrite(x, rel) for x in obj]
    if isinstance(obj, str):
        return obj.replace("${CLAUDE_PLUGIN_ROOT}", "${CLAUDE_PROJECT_DIR}/" + rel)
    return obj


def merge(dest, rel, hooks_path):
    try:
        with open(dest) as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    with open(hooks_path) as f:
        ours = _rewrite(json.load(f), rel)

    mine = "${CLAUDE_PROJECT_DIR}/" + rel + "/hooks/"
    cfg.setdefault("hooks", {})
    removed = 0
    for event in list(cfg["hooks"]):
        groups = []
        for g in cfg["hooks"][event]:
            kept = [h for h in g.get("hooks", []) if mine not in (h.get("command") or "")]
            removed += len(g.get("hooks", [])) - len(kept)
            if kept:
                groups.append(dict(g, hooks=kept))
        cfg["hooks"][event] = groups
    added = 0
    for event, groups in ours.items():
        cur = cfg["hooks"].setdefault(event, [])
        for g in groups:
            cur.append(g)
            added += len(g.get("hooks", []))

    allow = ['Bash(python3 "${{CLAUDE_PROJECT_DIR}}/{0}/hooks/csop.py")'.format(rel),
             'Bash(python3 "${{CLAUDE_PROJECT_DIR}}/{0}/hooks/csop.py" *)'.format(rel)]
    perm = cfg.setdefault("permissions", {}).setdefault("allow", [])
    added_perms = sum(1 for a in allow if a not in perm)
    perm.extend(a for a in allow if a not in perm)

    with open(dest, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    return added, removed, added_perms


if __name__ == "__main__":
    a, r, p = merge(sys.argv[1], sys.argv[2], sys.argv[3])
    print("{0} hooks synced, {1} stale removed, {2} permission(s)".format(a, r, p))
