---
description: CSOP -- climb the stage ladder: promote the current stage to its next stage.
argument-hint: "[<target-stage>]"
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/hooks/csop.py" *)
disable-model-invocation: true
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/csop.py" promote $ARGUMENTS`

Show the output above verbatim. No commentary.
