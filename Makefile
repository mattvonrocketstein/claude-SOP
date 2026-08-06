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
.PHONY: help init install validate ci check clean

help: ## Show available targets
	@echo "$(BOLD)CSOP make targets$(RESET)"
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  $(CYAN)%-7s$(RESET) %s\n",$$1,$$2}'

init: ## Enable CSOP in this repo (self-host)
	@$(PY) --version >/dev/null 2>&1 || { echo "$(RED)ERROR:$(RESET) python3 not on PATH (CSOP's only dependency)"; exit 1; }
	@$(PY) -c "import json;[json.load(open(f)) for f in ('.claude-plugin/plugin.json','hooks/hooks.json')]" \
	  && echo "$(GREEN)validated:$(RESET) manifest + wiring JSON"
	@if [ -f .claude/csop.json ]; then $(PY) -c "import sys;sys.path.insert(0,'hooks');import csop;csop.loads_jsonc(open('.claude/csop.json').read())" \
	  && echo "$(GREEN)validated:$(RESET) project config (json5)"; fi
	@for f in hooks/*.py; do $(PY) -c "import ast;ast.parse(open('$$f').read())" || exit 1; done; echo "$(GREEN)validated:$(RESET) hooks parse"
	@mkdir -p .claude/commands
	@cp -f commands/*.md .claude/commands/
	@sed -i 's#"$${CLAUDE_PLUGIN_ROOT}/hooks/csop.py"#hooks/csop.py#g' .claude/commands/*.md
	@echo "$(GREEN)materialized$(RESET) project commands -> .claude/commands/ (relative, pre-allowed)"
	@echo ""
	@echo "$(BOLD)CSOP is initialized for this repo:$(RESET)"
	@echo "  * $(CYAN)hooks$(RESET)   : wired in .claude/settings.json (approve workspace trust next session)"
	@echo "  * $(CYAN)enable$(RESET)  : /csop enable iso        (or bare: $(PY) hooks/csop.py enable iso)"
	@echo "  * $(CYAN)inspect$(RESET) : /csop  |  /csop catalog"

install: ## Wire CSOP into a consumer project (run from a submodule checkout)
	@root="$${DEST:-$$(git rev-parse --show-superproject-working-tree 2>/dev/null)}"; \
	 [ -n "$$root" ] || { echo "$(RED)ERROR:$(RESET) run from a submodule checkout, or pass DEST=<project-root>"; exit 1; }; \
	 rel="$$($(PY) -c 'import os,sys;print(os.path.relpath(os.getcwd(),sys.argv[1]))' "$$root")"; \
	 mkdir -p "$$root/.claude/commands"; \
	 dest="$$root/.claude/settings.json"; \
	 if [ -e "$$dest" ]; then \
	   echo "$(YELLOW)note:$(RESET) $$dest exists -- merge $$rel/hooks/hooks.json into its \"hooks\" (rewrite \$${CLAUDE_PLUGIN_ROOT} -> \$${CLAUDE_PROJECT_DIR}/$$rel)"; \
	 else \
	   { echo '{ "hooks":'; sed "s#\$${CLAUDE_PLUGIN_ROOT}#\$${CLAUDE_PROJECT_DIR}/$$rel#g" hooks/hooks.json; echo '}'; } > "$$dest"; \
	   echo "$(GREEN)wrote$(RESET) $$dest  (hooks -> $$rel/hooks/)"; \
	 fi; \
	 for f in commands/*.md; do sed "s#\"\$${CLAUDE_PLUGIN_ROOT}/hooks/csop.py\"#$$rel/hooks/csop.py#g" "$$f" > "$$root/.claude/commands/$$(basename "$$f")"; done; \
	 echo "$(GREEN)materialized$(RESET) /discipline /csop /disc -> .claude/commands/"; \
	 echo "next: gitignore $(CYAN).claude/csop-state/$(RESET) ; start a session in $$root and approve workspace trust"

check: ## Offline smoke-test hooks + CLI (no live session)
	@bash -c '\
	  set -u; D=$$(mktemp -d); export CLAUDE_PLUGIN_DATA=$$D CLAUDE_SESSION_ID=makecheck; \
	  $(PY) hooks/csop.py catalog >/dev/null && echo "cli catalog : $(GREEN)OK$(RESET)"; \
	  $(PY) hooks/csop.py enable iso >/dev/null && echo "cli enable  : $(GREEN)OK$(RESET)"; \
	  ev="{\"session_id\":\"makecheck\",\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git worktree add /tmp/x HEAD\"}}"; \
	  printf "%s" "$$ev" | $(PY) hooks/gate_bashverb.py >/dev/null 2>&1; \
	  test $$? -eq 2 && echo "gate block  : $(GREEN)OK$(RESET)" || { echo "gate block  : $(RED)FAIL$(RESET)"; exit 1; }; \
	  $(PY) -c "import sys;sys.path.insert(0,\"hooks\");import disciplines as d;bad=[r for x in d.DISCIPLINES for r in x.requires if not d.by_codename(r)];sys.exit(1 if bad else 0)" \
	    && echo "requires ok : $(GREEN)OK$(RESET)" || { echo "requires ok : $(RED)FAIL$(RESET)"; exit 1; }; \
	  $(PY) hooks/csop.py enable techwrite | grep -q hyg \
	    && echo "requires dep: $(GREEN)OK$(RESET)" || { echo "requires dep: $(RED)FAIL$(RESET)"; exit 1; }; \
	  $(PY) -c "import sys;sys.path.insert(0,\"hooks\");import disciplines as d;sys.exit(0 if d.FeatureSpike.spike_dir.startswith(d.Scratch.scratch_dir) and \"scratch/\" in d.FeatureSpike.render(\"reminder\") else 1)" \
	    && echo "sibling ref : $(GREEN)OK$(RESET)" || { echo "sibling ref : $(RED)FAIL$(RESET)"; exit 1; }; \
	  $(PY) hooks/csop.py enable iso >/dev/null; \
	  eve="{\"session_id\":\"makecheck\",\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"scratch/iso/mk/x\"}}"; \
	  evb="{\"session_id\":\"makecheck\",\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git worktree add scratch/iso/mk HEAD\"}}"; \
	  printf "%s" "$$eve" | $(PY) hooks/gate_isowrite.py >/dev/null 2>&1; test $$? -eq 2 && A=1 || A=0; \
	  printf "%s" "$$evb" | $(PY) hooks/gate_bashverb.py >/dev/null 2>&1; \
	  printf "%s" "$$eve" | $(PY) hooks/gate_isowrite.py >/dev/null 2>&1; test $$? -eq 0 && B=1 || B=0; \
	  test "$$A$$B" = "11" && echo "iso own     : $(GREEN)OK$(RESET)" || { echo "iso own     : $(RED)FAIL$(RESET)"; exit 1; }; \
	  $(PY) hooks/csop.py enable hacc >/dev/null; \
	  gc="{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git commit -m x\"}}"; \
	  gi="{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git -C scratch/iso/mk rebase main\"}}"; \
	  gp="{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git -C scratch/iso/mk push\"}}"; \
	  printf "%s" "$$gc" | $(PY) hooks/gate_git.py | grep -q deny && H1=1 || H1=0; \
	  printf "%s" "$$gi" | $(PY) hooks/gate_git.py | grep -q deny && H2=1 || H2=0; \
	  printf "%s" "$$gp" | $(PY) hooks/gate_git.py | grep -q deny && H3=1 || H3=0; \
	  test "$$H1$$H2$$H3" = "101" && echo "hacc iso    : $(GREEN)OK$(RESET)" || { echo "hacc iso    : $(RED)FAIL$(RESET)"; exit 1; }; \
	  $(PY) hooks/csop.py enable dream >/dev/null; \
	  do_="{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"src/x.py\"}}"; \
	  di="{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"scratch/x.py\"}}"; \
	  printf "%s" "$$do_" | $(PY) hooks/gate_dreamwrite.py | grep -q deny && M1=1 || M1=0; \
	  printf "%s" "$$di" | $(PY) hooks/gate_dreamwrite.py | grep -q deny && M2=1 || M2=0; \
	  test "$$M1$$M2" = "10" && echo "dream write : $(GREEN)OK$(RESET)" || { echo "dream write : $(RED)FAIL$(RESET)"; exit 1; }; \
	  P2=$$(mktemp -d); mkdir -p "$$P2/.claude"; \
	  printf "a\n# FROZEN\nsecret=1\n# END\nb\n" > "$$P2/conf.py"; \
	  printf "%s" "{ \"freeze\": {\"default_enabled\": true, \"frozen\": [ {\"path\":\"conf.py\",\"regex\":\"# FROZEN.*# END\"} ] } }" > "$$P2/.claude/csop.json"; \
	  ri="{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"conf.py\",\"old_string\":\"secret=1\"}}"; \
	  ro="{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"conf.py\",\"old_string\":\"a\"}}"; \
	  CLAUDE_PROJECT_DIR="$$P2" $(PY) hooks/csop.py enable freeze >/dev/null; \
	  printf "%s" "$$ri" | CLAUDE_PROJECT_DIR="$$P2" $(PY) hooks/gate_pathblock.py >/dev/null 2>&1; test $$? -eq 2 && G1=1 || G1=0; \
	  printf "%s" "$$ro" | CLAUDE_PROJECT_DIR="$$P2" $(PY) hooks/gate_pathblock.py >/dev/null 2>&1; test $$? -eq 0 && G2=1 || G2=0; \
	  test "$$G1$$G2" = "11" && echo "freeze region: $(GREEN)OK$(RESET)" || { echo "freeze region: $(RED)FAIL$(RESET)"; exit 1; }; \
	  rm -rf "$$P2"; \
	  rm -f -- "$$D"/*.json 2>/dev/null; rmdir "$$D" 2>/dev/null || true'

validate: ## Static sanity: every hook parses (py) + configs valid (json / jsonc)
	@bash -c '\
	  set -u; ok=1; \
	  for f in hooks/*.py; do \
	    $(PY) -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$$f" \
	      && echo "  py    $(GREEN)ok$(RESET)   $$f" || { echo "  py    $(RED)FAIL$(RESET) $$f"; ok=0; }; \
	  done; \
	  for f in .claude-plugin/plugin.json hooks/hooks.json .claude/settings.json; do \
	    [ -f "$$f" ] || continue; \
	    $(PY) -c "import json,sys; json.load(open(sys.argv[1]))" "$$f" \
	      && echo "  json  $(GREEN)ok$(RESET)   $$f" || { echo "  json  $(RED)FAIL$(RESET) $$f"; ok=0; }; \
	  done; \
	  for f in .claude/csop.json; do \
	    [ -f "$$f" ] || continue; \
	    $(PY) -c "import sys; sys.path.insert(0,\"hooks\"); import csop; csop.loads_jsonc(open(sys.argv[1]).read())" "$$f" \
	      && echo "  jsonc $(GREEN)ok$(RESET)   $$f" || { echo "  jsonc $(RED)FAIL$(RESET) $$f"; ok=0; }; \
	  done; \
	  test $$ok -eq 1 && echo "$(GREEN)validate:$(RESET) all sanity checks passed" || { echo "$(RED)validate: FAILURES$(RESET)"; exit 1; }'

ci: validate check ## Run the full offline CI gate (validate + check)

clean: ## Remove generated discovery surface + local state
	@rm -f -- .claude/commands/*.md 2>/dev/null || true
	@rmdir .claude/commands 2>/dev/null || true
	@rm -f -- .claude/csop-state/*.json 2>/dev/null || true
	@rmdir .claude/csop-state 2>/dev/null || true
	@echo "$(GREEN)cleaned$(RESET) generated .claude/commands + .claude/csop-state (settings.json kept)"
