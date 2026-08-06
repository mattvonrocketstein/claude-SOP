---
description: CSOP -- show the current stage and available stages, or set the current stage.
argument-hint: "[<stage-name>]"
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/hooks/csop.py" *)
disable-model-invocation: true
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/csop.py" stage $ARGUMENTS`

Show the output above verbatim. No commentary.
