---
description: CSOP -- deactivate a discipline (or `all`). Human-only, the inverse of `/csop enable`.
argument-hint: "<name|codename|all>"
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/hooks/csop.py" *)
disable-model-invocation: true
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/csop.py" disable $ARGUMENTS`

Show the output above verbatim. No commentary.
