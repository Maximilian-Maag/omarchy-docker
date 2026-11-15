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

# ── uninstall ─────────────────────────────────────────────────────────────────
# A dedicated, writable bin dir so the CLI symlink is exercised end to end without
# root: OMARCHY_DOCKER_BIN points install and uninstall at it, and the sudo stub is
# made to actually run the command it is handed (the dir needs no privilege).
cat > "$BIN/sudo" <<'SUDO'
#!/bin/bash
exec "$@"
SUDO
chmod +x "$BIN/sudo"
export OMARCHY_DOCKER_BIN="$SANDBOX/localbin"
mkdir -p "$OMARCHY_DOCKER_BIN"

# The user's own config, a require line they added by hand for a module that is not
# ours, and a manually-placed theme-set hook (what `omarchy hook install` would have
# written). All of it must be reason for the uninstall to act — or to leave alone —
# exactly as claimed.
printf -- '-- my own hyprland.lua\nhl.monitor({ output = "eDP-1" })\nrequire("hypr.my-own-module")\n' \
  > "$XDG_CONFIG_HOME/hypr/hyprland.lua"
mkdir -p "$XDG_CONFIG_HOME/omarchy/hooks/theme-set.d"
printf '#!/bin/bash\n' > "$XDG_CONFIG_HOME/omarchy/hooks/theme-set.d/docker-theme-set"
before="$(sha256sum "$XDG_CONFIG_HOME/hypr/hyprland.lua" | cut -d' ' -f1)"

bash "$INSTALL" >"$SANDBOX/install-u.log" 2>&1
if [[ -L "$OMARCHY_DOCKER_BIN/omarchy-docker" ]] \
   && [[ "$(readlink -f "$OMARCHY_DOCKER_BIN/omarchy-docker")" == "$ROOT/bin/omarchy-docker" ]]; then
  ok "install links the CLI into the override bin dir"
else
  bad "CLI not linked into the override bin dir"; cat "$SANDBOX/install-u.log"
fi

bash "$INSTALL" --uninstall >"$SANDBOX/uninstall.log" 2>&1
rc=$?
if (( rc == 0 )); then ok "uninstall exit 0"; else bad "uninstall exit $rc"; cat "$SANDBOX/uninstall.log"; fi

if [[ ! -e "$OMARCHY_DOCKER_BIN/omarchy-docker" ]]; then
  ok "the CLI symlink is removed"
else
  bad "CLI symlink survived the uninstall"
fi

if [[ "$(sha256sum "$XDG_CONFIG_HOME/hypr/hyprland.lua" | cut -d' ' -f1)" == "$before" ]]; then
  ok "install/uninstall round-trip leaves hyprland.lua byte-identical"
else
  bad "hyprland.lua changed across the round-trip"; cat "$XDG_CONFIG_HOME/hypr/hyprland.lua"
fi
n="$(grep -c -- '-- omarchy-docker keybindings' "$XDG_CONFIG_HOME/hypr/hyprland.lua" || true)"
if (( n == 0 )); then ok "no keybindings marker is left behind"; else bad "marker left behind ($n)"; fi
if grep -q 'hypr.my-own-module' "$XDG_CONFIG_HOME/hypr/hyprland.lua"; then
  ok "a hand-added require line survives the uninstall"
else
  bad "the user's hand-added require line was removed"
fi

if [[ ! -e "$XDG_CONFIG_HOME/hypr/docker-bindings.lua" ]]; then
  ok "the rendered bindings module is removed"
else
  bad "bindings module survived the uninstall"
fi

if [[ ! -e "$XDG_CONFIG_HOME/omarchy/hooks/theme-set.d/docker-theme-set" ]]; then
  ok "the theme-set hook is removed"
else
  bad "theme-set hook survived the uninstall"
fi

# The generated theme file is NOT an install artifact to reverse — the theme-set hook
# regenerates it, so an uninstall must leave it where it is.
if [[ -f "$XDG_CONFIG_HOME/docker/omarchy-docker-theme.json" ]]; then
  bash "$INSTALL" >/dev/null 2>&1
  bash "$INSTALL" --uninstall >/dev/null 2>&1
  if [[ -f "$XDG_CONFIG_HOME/docker/omarchy-docker-theme.json" ]]; then
    ok "the generated theme file is left alone by an uninstall"
  else
    bad "uninstall removed the generated theme file"
  fi
fi

# A symlink that points somewhere else is not ours: the uninstall says so and leaves it.
ln -sfn /bin/true "$OMARCHY_DOCKER_BIN/omarchy-docker"
out="$(bash "$INSTALL" --uninstall 2>&1)"
if [[ "$(readlink "$OMARCHY_DOCKER_BIN/omarchy-docker")" == "/bin/true" ]]; then
  ok "a foreign symlink is left alone"
else
  bad "uninstall touched a foreign symlink"
fi
if [[ $out == *"not a link into this checkout"* ]]; then
  ok "and the refusal is reported"
else
  bad "uninstall did not say why it left the foreign symlink"; printf '%s\n' "$out"
fi
rm -f "$OMARCHY_DOCKER_BIN/omarchy-docker"

# A bare require line for OUR module, added by hand with no marker above it, is the
# user's own line — install never writes one without the marker — so it survives too,
# and the config comes back byte-identical.
printf -- '-- my own hyprland.lua\nrequire("hypr.docker-bindings")\n' \
  > "$XDG_CONFIG_HOME/hypr/hyprland.lua"
before2="$(sha256sum "$XDG_CONFIG_HOME/hypr/hyprland.lua" | cut -d' ' -f1)"
bash "$INSTALL" >/dev/null 2>&1
bash "$INSTALL" --uninstall >/dev/null 2>&1
if [[ "$(sha256sum "$XDG_CONFIG_HOME/hypr/hyprland.lua" | cut -d' ' -f1)" == "$before2" ]]; then
  ok "a hand-added bare require line survives the round-trip too"
else
  bad "a hand-added bare require line was removed"; cat "$XDG_CONFIG_HOME/hypr/hyprland.lua"
fi

# Uninstalling when nothing is installed is not an error (idempotent teardown).
bash "$INSTALL" --uninstall >/dev/null 2>&1
if (( $? == 0 )); then ok "uninstalling nothing succeeds"; else bad "uninstalling nothing failed"; fi

echo
if (( fail == 0 )); then echo "shell: all $pass passed"; exit 0; else echo "shell: $fail failed"; exit 1; fi
