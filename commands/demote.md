---
description: CSOP -- step down the stage ladder: demote the current stage to a `from` source.
argument-hint: "[<target-stage>]"
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/hooks/csop.py" *)
disable-model-invocation: true
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/csop.py" demote $ARGUMENTS`

Show the output above verbatim. No commentary.
