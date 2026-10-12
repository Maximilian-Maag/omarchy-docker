#!/bin/bash
# Shell tests for hooks/docker-theme-set — hermetic (throwaway HOME/XDG, no docker).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$ROOT/hooks/docker-theme-set"
pass=0; fail=0
ok()  { echo "  ok: $*"; pass=$((pass+1)); }
bad() { echo "  FAIL: $*"; fail=$((fail+1)); }

setup() {
  SANDBOX="$(mktemp -d)"
  export HOME="$SANDBOX/home"
  export XDG_STATE_HOME="$SANDBOX/state"
  export XDG_CONFIG_HOME="$SANDBOX/config"
  export XDG_DATA_HOME="$SANDBOX/data"
  mkdir -p "$HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME"
  mkdir -p "$XDG_STATE_HOME/omarchy/current/theme"
  cat > "$XDG_STATE_HOME/omarchy/current/theme/colors.toml" <<'TOML'
mode = "dark"
accent = "#82FB9C"
selection = "#1f253a"
muted = "#2d3450"
background = "#0B0C16"
foreground = "#ddf7ff"
TOML
}

teardown() { rm -rf "$SANDBOX"; }
THEME_FILE() { printf '%s\n' "$XDG_CONFIG_HOME/docker/omarchy-docker-theme.json"; }

# 1. plugin found -> the theme file is generated
setup
export OMARCHY_DOCKER_DIR="$ROOT"
bash "$HOOK" "Hackerman"; rc=$?
if [[ -f "$(THEME_FILE)" ]]; then ok "theme file generated from the applied theme"; else bad "no theme file written"; fi
if (( rc == 0 )); then ok "hook exit 0"; else bad "hook exit $rc"; fi
if grep -q "82FB9C" "$(THEME_FILE)"; then ok "theme file carries the applied accent"; else bad "wrong colours"; fi
teardown

# 2. empty theme name -> no-op (kills the -z guard mutation)
setup
export OMARCHY_DOCKER_DIR="$ROOT"
bash "$HOOK" ""; rc=$?
if [[ ! -e "$(THEME_FILE)" ]]; then ok "empty theme writes nothing"; else bad "empty theme generated a file"; fi
if (( rc == 0 )); then ok "empty theme exit 0"; else bad "empty theme exit $rc"; fi
teardown

# 3. plugin not found -> graceful no-op
setup
export OMARCHY_DOCKER_DIR="$SANDBOX/nope"
bash "$HOOK" "Hackerman"; rc=$?
if (( rc == 0 )); then ok "missing plugin exit 0"; else bad "missing plugin exit $rc"; fi
if [[ ! -e "$(THEME_FILE)" ]]; then ok "missing plugin writes nothing"; else bad "wrote without a plugin"; fi
teardown

# 4. self-location fallback (kills the && -> || mutation in find_plugin)
setup
mkdir -p "$HOME/Work"
ln -s "$ROOT" "$HOME/Work/omarchy-docker"
export OMARCHY_DOCKER_DIR="$SANDBOX/emptydir"
mkdir -p "$OMARCHY_DOCKER_DIR"
bash "$HOOK" "Hackerman"
if [[ -f "$(THEME_FILE)" ]]; then ok "fell back to the dev checkout"; else bad "did not self-locate"; fi
teardown

# 5. a failing CLI must not abort the hook (kills the || -> && mutation)
setup
export OMARCHY_DOCKER_DIR="$ROOT"
rm -f "$XDG_STATE_HOME/omarchy/current/theme/colors.toml"
bash "$HOOK" "Hackerman"; rc=$?
if (( rc == 0 )); then ok "hook survives a CLI failure"; else bad "CLI failure aborted the hook (exit $rc)"; fi
teardown

# 6. a title-cased, spaced theme name is accepted (kills the ${1:-} -> ${2:-} mutation)
setup
export OMARCHY_DOCKER_DIR="$ROOT"
bash "$HOOK" "Tokyo Night"; rc=$?
if [[ -f "$(THEME_FILE)" ]]; then ok "spaced theme name still generates the file"; else bad "spaced theme name lost"; fi
if (( rc == 0 )); then ok "spaced theme exit 0"; else bad "spaced theme exit $rc"; fi
teardown

echo
if (( fail == 0 )); then echo "shell: all $pass passed"; exit 0; else echo "shell: $fail failed"; exit 1; fi
