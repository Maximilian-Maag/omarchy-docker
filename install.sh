#!/bin/bash
# omarchy-docker install script. Run once after cloning, or re-run to update:
#
#   ./install.sh                     install / update everything
#   ./install.sh --uninstall         remove what this script installed, and only that
#   OMARCHY_DOCKER_BIN=~/.local/bin ./install.sh   where the CLI is symlinked
#
# The CLI goes into a bin directory (default /usr/local/bin, on PATH); the
# theme-set hook is an `omarchy hook install`; the keybinding module and its
# require block live in the Hyprland config dir. `--uninstall` reverses exactly
# those, and leaves the user's own config values and the generated theme artifact
# (which the theme-set hook regenerates) alone.
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BIN_DIR="${OMARCHY_DOCKER_BIN:-/usr/local/bin}"
BIN_SRC="$PLUGIN_DIR/bin/omarchy-docker"
BIN_DEST="$BIN_DIR/omarchy-docker"

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
HYPR_CONFIG_DIR="$CONFIG_DIR/hypr"
HYPR_MAIN="$HYPR_CONFIG_DIR/hyprland.lua"
BINDINGS="$HYPR_CONFIG_DIR/docker-bindings.lua"
REQUIRE_LINE='require("hypr.docker-bindings")'
BINDINGS_MARKER='-- omarchy-docker keybindings'
HOOK_DEST="$CONFIG_DIR/omarchy/hooks/theme-set.d/docker-theme-set"

# ── helpers ───────────────────────────────────────────────────────────────────
remove_path() {  # remove_path <path> — remove a file we installed; sudo only if the dir needs it
  local path="$1"
  if (( EUID == 0 )) || [[ -w "$(dirname "$path")" ]]; then
    rm -f "$path"
  elif command -v sudo >/dev/null 2>&1; then
    sudo rm -f "$path"
  else
    return 1
  fi
}

unlink_ours() {  # unlink_ours <dest> <source it must point at>
  local dest="$1" source="$2"
  if [[ -L $dest ]] && [[ "$(readlink -f "$dest")" == "$(readlink -f "$source")" ]]; then
    remove_path "$dest" && echo "  Removed $dest."
  elif [[ -e $dest ]]; then
    echo "  WARNING: $dest is not a link into this checkout — left alone."
  fi
}

uninstall() {
  echo "omarchy-docker: uninstalling from $PLUGIN_DIR"

  # 1. The CLI symlink, and only if it points back into this checkout.
  unlink_ours "$BIN_DEST" "$BIN_SRC"

  # 2. The Hyprland keybinding module install rendered into the config dir.
  if [[ -f $BINDINGS ]]; then
    rm -f "$BINDINGS"
    echo "  Removed $BINDINGS."
  fi

  # 3. The require block install appended to hyprland.lua. Removed by exact line
  #    — never `sed -i` — so the user's config is only ever rewritten one line
  #    smaller. install writes the block as a blank line, a
  #    `-- omarchy-docker keybindings` marker, then the require line, so the whole
  #    block comes back out: leaving the marker (and its blank line) behind would
  #    stack another marker on the file at every install/uninstall cycle.
  if [[ -f $HYPR_MAIN ]] && grep -qF "$REQUIRE_LINE" "$HYPR_MAIN"; then
    kept=""
    mapfile -t lines < "$HYPR_MAIN"
    out=()
    removed=0
    for line in "${lines[@]}"; do
      # Only the require line install appended — one sitting directly under our
      # marker comment — is ours to take back. A require line with no marker above
      # it was added by hand (or by an older version), so it is the user's and it
      # survives.
      if [[ $line == "$REQUIRE_LINE" ]] && (( ${#out[@]} )) && [[ ${out[-1]} == "$BINDINGS_MARKER" ]]; then
        unset 'out[-1]'
        if (( ${#out[@]} )) && [[ -z ${out[-1]} ]]; then
          unset 'out[-1]'
        fi
        removed=1
        continue
      fi
      out+=("$line")
    done
    if (( removed )); then
      kept="$(mktemp)"
      for line in ${out[@]+"${out[@]}"}; do
        printf '%s\n' "$line"
      done > "$kept"
      mv "$kept" "$HYPR_MAIN"
      echo "  Took the require line back out of $HYPR_MAIN."
    fi
  fi

  # 4. The theme-set hook, if `omarchy hook install` put one there.
  if [[ -f $HOOK_DEST ]]; then
    rm -f "$HOOK_DEST"
    echo "  Removed the theme-set hook."
  fi

  echo ""
  echo "Done. The generated theme file and your config values were left as they are."
  echo "Reload Hyprland config:  hyprctl reload"
}

if [[ ${1:-} == --uninstall ]]; then
  uninstall
  exit 0
fi

echo "omarchy-docker: installing from $PLUGIN_DIR"

# ── 1. Validate the plugin ────────────────────────────────────────────────────
if command -v omarchy >/dev/null 2>&1; then
  omarchy plugin validate "$PLUGIN_DIR" && echo "  manifest OK."
fi

# ── 2. Put the CLI on PATH (symlink, so git pull keeps it current) ────────────
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
# The binding is RENDERED from config/docker.json's "keybinding" value by the CLI
# (`bindings`), not copied verbatim, so editing the config changes what installs.
if [[ -f "$HYPR_MAIN" ]]; then
  "$BIN_SRC" bindings
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
