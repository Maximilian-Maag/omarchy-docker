#!/bin/bash
# omarchy-docker install script. Run once after cloning, or re-run to update.
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "omarchy-docker: installing from $PLUGIN_DIR"

# ── 1. Validate the plugin ────────────────────────────────────────────────────
if command -v omarchy >/dev/null 2>&1; then
  omarchy plugin validate "$PLUGIN_DIR" && echo "  manifest OK."
fi

# ── 2. Put the CLI on PATH (symlink, so git pull keeps it current) ────────────
BIN_SRC="$PLUGIN_DIR/bin/omarchy-docker"
BIN_DEST="/usr/local/bin/omarchy-docker"
chmod +x "$BIN_SRC"
if [[ -L "$BIN_DEST" ]] && [[ "$(readlink -f "$BIN_DEST")" == "$(readlink -f "$BIN_SRC")" ]]; then
  echo "  omarchy-docker already on PATH."
elif (( EUID == 0 )); then
  ln -sf "$BIN_SRC" "$BIN_DEST" && echo "  Installed $BIN_DEST."
elif command -v sudo >/dev/null 2>&1; then
  sudo ln -sf "$BIN_SRC" "$BIN_DEST" && echo "  Installed $BIN_DEST."
else
  echo "  WARNING: no sudo — add $BIN_SRC to PATH manually."
fi

# ── 3. Generate the theme file now ────────────────────────────────────────────
"$BIN_SRC" theme || echo "  WARNING: no applied theme yet — run 'omarchy-docker theme' later."

# ── 4. Report (never silently "fix") the docker group membership ──────────────
if command -v docker >/dev/null 2>&1; then
  if "$BIN_SRC" status | grep -q "user groups   : member"; then
    echo "  This user can reach the Docker daemon."
  else
    echo "  NOTE: this user is not in the docker group (or the daemon is down)."
    echo "        Fix with:  sudo usermod -aG docker \$USER   then log out and back in."
  fi
fi

# ── 5. Theme-set hook (uniquely named to avoid basename collisions) ───────────
chmod +x "$PLUGIN_DIR/hooks/docker-theme-set"
if command -v omarchy >/dev/null 2>&1; then
  omarchy hook install theme-set "$PLUGIN_DIR/hooks/docker-theme-set"
  echo "  Installed theme-set hook (as docker-theme-set)."
fi

# ── 6. Wire OS keybindings into Hyprland ──────────────────────────────────────
HYPR_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/hypr"
HYPR_MAIN="$HYPR_CONFIG_DIR/hyprland.lua"
if [[ -f "$HYPR_MAIN" ]]; then
  cp "$PLUGIN_DIR/bin/bindings.lua" "$HYPR_CONFIG_DIR/docker-bindings.lua"
  if ! grep -q "docker-bindings" "$HYPR_MAIN"; then
    printf '\n-- omarchy-docker keybindings\nrequire("hypr.docker-bindings")\n' >> "$HYPR_MAIN"
    echo "  Wired keybindings into $HYPR_MAIN"
  else
    echo "  Keybindings already wired (updated)."
  fi
else
  echo "  WARNING: $HYPR_MAIN not found — add: require(\"hypr.docker-bindings\")"
fi

echo ""
echo "Done. Try:  omarchy-docker status   /   omarchy-docker list"
