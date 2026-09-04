# CSOP -- self-hosting init + dev helpers.
#
# `make init` enables CSOP in THIS repo (self-host). The hooks are already wired
# via .claude/settings.json; init validates the plugin and materializes the
# slash-command discovery surface under .claude/commands/ (project commands load
# ONLY from there, not the top-level plugin-layout commands/). The generated
# .claude/commands/ is gitignored and regenerable -- re-run `make init` after
# changing commands/. The canonical source stays the top-level plugin layout.

SHELL := bash
PY    := python3
REQ_CC := 2.1.196

# ANSI colors -- real ESC bytes so plain `echo` renders them; unset with NO_COLOR=1.
ESC    := $(shell printf '\033')
BOLD   := $(ESC)[1m
DIM    := $(ESC)[2m
RED    := $(ESC)[31m
GREEN  := $(ESC)[32m
YELLOW := $(ESC)[33m
CYAN   := $(ESC)[36m
RESET  := $(ESC)[0m
ifdef NO_COLOR
BOLD :=
DIM :=
RED :=
GREEN :=
YELLOW :=
CYAN :=
RESET :=
endif

.DEFAULT_GOAL := help
.PHONY: help init install test validate ci check clean version-check update.siblings

# Where `update.siblings` looks for consumer projects; override on the CLI.
SIBLING_ROOT ?= $(HOME)/code

# A vendored checkout is a pinned mirror, so it is reset onto upstream, not pulled.

help: ## Show available targets
	@echo "$(BOLD)CSOP make targets$(RESET)"
	@grep -E '^[a-zA-Z_.-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  $(CYAN)%-16s$(RESET) %s\n",$$1,$$2}'

version-check: ## Verify Claude Code is new enough for ${CLAUDE_PROJECT_DIR} in slash commands
	@if [ -n "$(SKIP_VERSION_CHECK)" ]; then echo "$(GREEN)skip:$(RESET) version check (SKIP_VERSION_CHECK set)"; exit 0; fi; \
	 ver="$$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"; \
	 if [ -z "$$ver" ] && [ -n "$$CLAUDE_CODE_EXECPATH" ] && [ -x "$$CLAUDE_CODE_EXECPATH" ]; then \
	   ver="$$("$$CLAUDE_CODE_EXECPATH" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"; \
	   [ -n "$$ver" ] && echo "$(DIM)note:$(RESET) 'claude' not on PATH (entrypoint: $${CLAUDE_CODE_ENTRYPOINT:-unknown}); used \$$CLAUDE_CODE_EXECPATH instead"; \
	 fi; \
	 if [ -z "$$ver" ]; then echo "$(RED)error:$(RESET) 'claude' CLI not found on PATH or via \$$CLAUDE_CODE_EXECPATH; CSOP slash commands need Claude Code >= $(REQ_CC). (bypass: make ... SKIP_VERSION_CHECK=1)"; exit 1; fi; \
	 $(PY) -c "import sys;c=tuple(map(int,'$$ver'.split('.')));r=tuple(map(int,'$(REQ_CC)'.split('.')));sys.exit(0 if c>=r else 1)" \
	   || { echo "$(RED)refusing:$(RESET) Claude Code $$ver is too old. CSOP slash commands resolve csop.py via \$${CLAUDE_PROJECT_DIR}, which is substituted in a command body only on $(REQ_CC)+. Upgrade the CLI, then re-run. (bypass at your own risk: make ... SKIP_VERSION_CHECK=1)"; exit 1; }; \
	 echo "$(GREEN)ok:$(RESET) Claude Code $$ver (>= $(REQ_CC))"

init: version-check ## Enable CSOP in this repo (self-host)
	@$(PY) --version >/dev/null 2>&1 || { echo "$(RED)ERROR:$(RESET) python3 not on PATH (CSOP's only dependency)"; exit 1; }
	@$(PY) -c "import json;[json.load(open(f)) for f in ('.claude-plugin/plugin.json','hooks/hooks.json')]" \
	  && echo "$(GREEN)validated:$(RESET) manifest + wiring JSON"
	@if [ -f .claude/csop.json ]; then $(PY) -c "import sys;sys.path.insert(0,'hooks');import csop;csop.loads_jsonc(open('.claude/csop.json').read())" \
	  && echo "$(GREEN)validated:$(RESET) project config (json5)"; fi
	@for f in hooks/*.py; do $(PY) -c "import ast;ast.parse(open('$$f').read())" || exit 1; done; echo "$(GREEN)validated:$(RESET) hooks parse"
	@$(PY) tools/sync_commands.py commands .claude/commands .
	@echo "$(GREEN)materialized$(RESET) project commands -> .claude/commands/ (CLAUDE_PROJECT_DIR-anchored; needs Claude Code v2.1.196+)"
	@echo ""
	@echo "$(BOLD)CSOP is initialized for this repo:$(RESET)"
	@echo "  * $(CYAN)hooks$(RESET)   : wired in .claude/settings.json (approve workspace trust next session)"
	@echo "  * $(CYAN)enable$(RESET)  : /sop enable iso         (or bare: $(PY) hooks/csop.py enable iso)"
	@echo "  * $(CYAN)inspect$(RESET) : /sop  |  /sop catalog"

install: version-check ## Wire CSOP into a consumer project (run from a submodule checkout)
	@root="$${DEST:-$$(git rev-parse --show-superproject-working-tree 2>/dev/null)}"; \
	 [ -n "$$root" ] || { echo "$(RED)error:$(RESET) run from a submodule checkout, or pass DEST=<project-root>"; exit 1; }; \
	 rel="$$($(PY) -c 'import os,sys;print(os.path.relpath(os.path.realpath(os.getcwd()),os.path.realpath(sys.argv[1])))' "$$root")"; \
	 mkdir -p "$$root/.claude/commands"; \
	 merged="$$($(PY) tools/merge_settings.py "$$root/.claude/settings.json" "$$rel" hooks/hooks.json)"; \
	 cmdlog="$$($(PY) tools/sync_commands.py commands "$$root/.claude/commands" "$$rel")" || exit 1; \
	 gi="$$root/.gitignore"; \
	 if [ -f "$$gi" ] && grep -qxF ".claude/csop-state/" "$$gi"; then gi_st="already ignored"; else printf '%s\n' ".claude/csop-state/" >> "$$gi"; gi_st="added .claude/csop-state/ (runtime state)"; fi; \
	 printf '\n$(BOLD)CSOP installed$(RESET) into %s\n\n$(BOLD)changed$(RESET)\n' "$$root"; \
	 printf '  %-24s %s\n' ".claude/settings.json" "merged CSOP hooks and permissions.allow ($$merged), preserving your settings"; \
	 printf '  %-24s %s\n' ".claude/commands/" "synced (a command CSOP has retired is pruned; anything else is left alone)"; \
	 printf '%s\n' "$$cmdlog"; \
	 printf '  %-24s %s\n' ".gitignore" "$$gi_st"; \
	 printf '\nActive on your next Claude Code session here. hacc, scratch, hyg are on by default; %s adds more.\n' "$(CYAN)/sop enable <name>$(RESET)"

test: ## Run the offline test suite (tests/test_csop.py)
	@$(PY) -m unittest -v tests.test_csop

check: ## Offline test suite: static sanity + gates + CLI + config resolution
	@$(PY) -m unittest -v tests.test_csop

validate: ## Static sanity: hooks parse + configs valid (json / jsonc)
	@$(PY) -m unittest -v tests.test_csop.StaticChecks

ci: validate check ## Run the full offline CI gate (validate + check)

update.siblings: version-check ## Reset every .claude/csop submodule under ~/code (SIBLING_ROOT) to upstream, then re-wire it
	@root="$(SIBLING_ROOT)"; \
	 [ -d "$$root" ] || { echo "$(RED)error:$(RESET) $$root is not a directory (override with SIBLING_ROOT=<path>)"; exit 1; }; \
	 echo "$(BOLD)scanning$(RESET) $$root for .claude/csop submodules"; \
	 found=0; ok=0; fail=0; \
	 while IFS= read -r d; do \
	   git -C "$$d" rev-parse --git-dir >/dev/null 2>&1 || continue; \
	   super="$$(git -C "$$d" rev-parse --show-superproject-working-tree 2>/dev/null)"; \
	   [ -n "$$super" ] || { echo "  $(DIM)skip$(RESET)  $$d (not a submodule)"; continue; }; \
	   found=$$((found+1)); \
	   ins=""; \
	   if [ -n "$$(git -C "$$d" status --porcelain --untracked-files=no 2>/dev/null)" ]; then \
	     fail=$$((fail+1)); \
	     echo "  $(RED)fail$(RESET)  $$d $(DIM)(tracked local edits; commit or discard them, then re-run)$(RESET)"; \
	     continue; \
	   fi; \
	   up="$$(git -C "$$d" rev-parse --abbrev-ref '@{u}' 2>/dev/null)"; \
	   [ -n "$$up" ] || up="origin/$$(git -C "$$d" rev-parse --abbrev-ref HEAD 2>/dev/null)"; \
	   if out="$$(git -C "$$d" fetch --prune 2>&1 && git -C "$$d" reset --hard "$$up" 2>&1)" \
	      && ins="$$($(MAKE) -s -C "$$d" install NO_COLOR=1 SKIP_VERSION_CHECK=1 2>&1)"; then \
	     ok=$$((ok+1)); \
	     echo "  $(GREEN)ok$(RESET)    $$d"; \
	     printf '%s\n' "$$ins" | sed 's/^/        /'; \
	   else \
	     fail=$$((fail+1)); \
	     echo "  $(RED)fail$(RESET)  $$d"; \
	     printf '%s\n%s\n' "$$out" "$$ins" | sed 's/^/        /'; \
	   fi; \
	 done < <(find "$$root" -type d -name .claude -not -path '*/.git/*' -exec test -d '{}/csop' \; -print 2>/dev/null | sed 's#$$#/csop#' | sort); \
	 echo "$(BOLD)done$(RESET) $$found submodule(s): $(GREEN)$$ok ok$(RESET), $(RED)$$fail failed$(RESET)"; \
	 [ "$$fail" -eq 0 ]

clean: ## Remove generated discovery surface + local state
	@rm -f -- .claude/commands/*.md 2>/dev/null || true
	@rmdir .claude/commands 2>/dev/null || true
	@rm -f -- .claude/csop-state/*.json 2>/dev/null || true
	@rmdir .claude/csop-state 2>/dev/null || true
	@echo "$(GREEN)cleaned$(RESET) generated .claude/commands + .claude/csop-state (settings.json kept)"
