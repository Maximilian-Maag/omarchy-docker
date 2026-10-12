#!/bin/bash
# Shell tests for install.sh — hermetic (throwaway HOME/XDG, stubbed omarchy/sudo/docker).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL="$ROOT/install.sh"
pass=0; fail=0
ok()  { echo "  ok: $*"; pass=$((pass+1)); }
bad() { echo "  FAIL: $*"; fail=$((fail+1)); }

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT
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

# stub omarchy / sudo / docker, first on PATH
BIN="$SANDBOX/bin"; mkdir -p "$BIN"; export PATH="$BIN:$PATH"
printf '#!/bin/bash\nexit 0\n' > "$BIN/omarchy"
printf '#!/bin/bash\nexit 0\n' > "$BIN/sudo"
cat > "$BIN/docker" <<'DOCKER'
#!/bin/bash
if [[ "${1:-}" == "info" ]]; then exit 1; fi
exit 0
DOCKER
cat > "$BIN/getent" <<'GETENT'
#!/bin/bash
printf 'docker:x:966:mmaag\n'
exit 0
GETENT
chmod +x "$BIN/omarchy" "$BIN/sudo" "$BIN/docker" "$BIN/getent"

mkdir -p "$XDG_CONFIG_HOME/hypr"
printf -- '-- main config\n' > "$XDG_CONFIG_HOME/hypr/hyprland.lua"

bash "$INSTALL" >"$SANDBOX/install.log" 2>&1
rc=$?

if (( rc == 0 )); then ok "install.sh exit 0"; else bad "install.sh exit $rc"; cat "$SANDBOX/install.log"; fi

if [[ -f "$XDG_CONFIG_HOME/docker/omarchy-docker-theme.json" ]]; then
  ok "theme file generated"
else
  bad "theme file not generated"
fi
if [[ -f "$XDG_CONFIG_HOME/hypr/docker-bindings.lua" ]]; then
  ok "hyprland bindings module installed"
else
  bad "bindings module missing"
fi
if grep -q "hypr.docker-bindings" "$XDG_CONFIG_HOME/hypr/hyprland.lua"; then
  ok "keybindings wired into hyprland.lua"
else
  bad "keybindings not wired"
fi
if grep -q "docker-theme-set" "$SANDBOX/install.log"; then
  ok "uniquely-named hook installed"
else
  bad "hook not installed under its unique name"
fi

# re-running must not duplicate the require line
bash "$INSTALL" >"$SANDBOX/install2.log" 2>&1
n="$(grep -c 'hypr.docker-bindings' "$XDG_CONFIG_HOME/hypr/hyprland.lua")"
if (( n == 1 )); then ok "idempotent: one require line"; else bad "duplicated require line ($n)"; fi

echo
if (( fail == 0 )); then echo "shell: all $pass passed"; exit 0; else echo "shell: $fail failed"; exit 1; fi
