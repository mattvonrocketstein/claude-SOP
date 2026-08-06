#!/usr/bin/env python3
"""SessionStart hook: wipe per-session discipline state on /clear or startup.

Makes "/clear disarms all disciplines" real: because /clear may not rotate the
session_id, stale active-state must be cleared explicitly. Fail-open.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csop  # noqa: E402
import disciplines  # noqa: E402


def main():
    event = csop.load_event()
    if (event.get("source", "") or "") in ("clear", "startup"):
        csop.reset(disciplines.closure(disciplines.defaults()))
        csop.seed_stage()
        for aux in ("iso-trees.json", "notices.json"):
            try:
                os.remove(csop.state_path(aux))
            except OSError:
                pass
    sys.exit(0)


if __name__ == "__main__":
    main()
