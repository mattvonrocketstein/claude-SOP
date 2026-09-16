---
description: CSOP -- show the declared ticket, or declare one over the current stage.
argument-hint: "[<issue-id>]"
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/hooks/csop.py" *)
disable-model-invocation: true
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/csop.py" ticket $ARGUMENTS`

Show the output above verbatim. No commentary.
