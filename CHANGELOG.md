# Changelog

All notable changes to omarchy-docker are documented here. The newest heading must
equal `version` in `manifest.json` (enforced by the policy check).

## [0.2.0] - 2026-11-15

### Added

- `./install.sh --uninstall` — reverses exactly what the installer added: the
  `/usr/local/bin` symlink (only if it points back into this checkout), the rendered
  keybinding module and its `require` block in `hyprland.lua`, and the theme-set
  hook. The user's own config values and the generated theme file (which the
  theme-set hook regenerates) are left untouched, and a require line with no
  `-- omarchy-docker keybindings` marker above it — added by hand — survives.
- `OMARCHY_DOCKER_BIN` — overrides where the CLI is symlinked (default
  `/usr/local/bin`), so an install without root and the shell tests use a private
  bin dir.
- A shell round-trip test asserting that an install → uninstall cycle leaves the
  user's `hyprland.lua` byte-identical (sha256) and leaves no marker or blank line
  behind.

## [0.1.0] - 2026-10-12

### Added

- `omarchy-docker list` — containers in a table coloured from the applied Omarchy
  theme, read live from
  `~/.local/state/omarchy/current/theme/colors.toml` (no baked-in palette).
- `omarchy-docker status` — reports whether the Docker daemon is reachable and
  whether this user is in the `docker` group, with the exact fix when they are not.
- `omarchy-docker start|stop|restart|logs|exec` — wrap the docker CLI through a
  single injectable runner seam.
- `omarchy-docker theme` — renders the container view's colour roles from the
  applied theme, to a file (`--stdout` to print).
- `hooks/docker-theme-set` — uniquely named `theme-set` hook that regenerates the
  colour roles on a theme change. Self-locating (an installed hook cannot find its
  plugin via `$(dirname "$BASH_SOURCE")/..`).
- `bin/bindings.lua` — Hyprland keybinding (Super+Shift+Alt+D) that opens the
  container view in a floating terminal.
- `config/docker.json` — keybinding, theme file path and the listing row cap.
- Full test harness: unit, regression, integration, e2e and shell tests plus
  measured mutation testing, policy-as-code and CI.
