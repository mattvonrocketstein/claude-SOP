---
description: CSOP -- enable / list / catalog / show disciplines (SOPs); no-arg = list.
argument-hint: "enable <name|codename> | list | catalog | show <name>"
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/hooks/csop.py" *)
disable-model-invocation: true
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/csop.py" $ARGUMENTS`

Show the output above verbatim. No commentary.
