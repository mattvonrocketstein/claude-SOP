---
description: Alias of /discipline -- CSOP discipline manager (enable | list | catalog); no-arg = list.
argument-hint: "enable <name|codename> | list | catalog"
allowed-tools: Bash(python3 hooks/csop.py *)
disable-model-invocation: true
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/csop.py" $ARGUMENTS`

Show the output above verbatim. No commentary.
