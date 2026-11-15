# omarchy-docker

Integrates **Docker** with the **Omarchy** desktop: a themed container view, the
everyday lifecycle commands, a daemon/group check, and a Hyprland keybinding that
opens the view in a floating terminal.

- Reads the applied theme **live** from
  `~/.local/state/omarchy/current/theme/colors.toml` on every run — **no palette
  is baked in**, so every Omarchy theme (including one you wrote yourself) colours
  the container view correctly.
- `status` tells you the truth about this machine: whether the daemon answers and
  whether you are in the `docker` group — and prints the exact fix when you are not.
- A uniquely-named `theme-set` hook (`hooks/docker-theme-set`) regenerates the
  colour roles whenever you change theme. `theme` writes those roles to
  `~/.config/docker/omarchy-docker-theme.json`, and `list` **reads that file** —
  so the hook has a real effect (a theme change updates the view) rather than
  regenerating something nothing consumes.

Plugin id: `Maximilian-Maag.docker`.

## Install

```bash
git clone <this repo> ~/Work/omarchy-docker
cd ~/Work/omarchy-docker
./install.sh
```

Or, as an Omarchy plugin:

```bash
omarchy plugin add <repo-url> --yes
```

`install.sh` symlinks the CLI into `/usr/local/bin`, generates the theme file,
installs the hook and wires the keybinding into `hyprland.lua`. It **never**
changes your group membership — it only reports if you need to.

To reverse it, `./install.sh --uninstall` removes exactly what the installer
added — the `/usr/local/bin` symlink (only if it points back into this checkout),
the rendered keybinding module and its `require` block, and the theme-set hook —
and leaves your own config values and the generated theme file alone. Set
`OMARCHY_DOCKER_BIN` (default `/usr/local/bin`) to symlink somewhere else.

## Usage

```bash
omarchy-docker status          # daemon reachable? in the docker group?
omarchy-docker list            # containers, coloured from the applied theme
omarchy-docker start web       # start / stop / restart by name
omarchy-docker stop web
omarchy-docker restart web
omarchy-docker logs web --tail 50
omarchy-docker exec web -- env                 # run a command inside a container
omarchy-docker theme           # write ~/.config/docker/omarchy-docker-theme.json
omarchy-docker theme --stdout  # print the colour roles instead
omarchy-docker bindings        # render ~/.config/hypr/docker-bindings.lua from the config
```

`list` shows NAME, IMAGE, STATE and STATUS. Rows are painted with the theme colour
that matches the container's state (running / stopped / other). Colours come from
the generated theme file if it exists, otherwise from the applied `colors.toml` read
live. The cap on rows is `max_rows` in `config/docker.json`.

## Reaching the Docker daemon

By default only `root` and members of the `docker` group may talk to the daemon.
If `omarchy-docker status` reports **not a member**, add yourself once and re-login:

```bash
sudo usermod -aG docker $USER   # then log out and back in (or reboot)
```

That is deliberately a manual step: joining the `docker` group is equivalent to
passwordless root on the host, so this plugin never does it silently. On the
machine this plugin was built on, `mmaag` is already in the `docker` group
(`docker:x:966:mmaag`), so `status` reports `member` and `reachable`.

## Keybinding

`Super+Shift+Alt+D` opens the container view in a floating terminal. It is
**rendered from `config/docker.json`'s `keybinding`** by `omarchy-docker bindings`
(run by `install.sh`): `bin/bindings.lua` is a template whose placeholder the CLI
substitutes, and the result is written to `~/.config/hypr/docker-bindings.lua` and
required from `hyprland.lua`. Editing the config therefore changes the installed
binding.

## Configuration

`config/docker.json` (read by the CLI):

```json
{
  "keybinding": "SUPER + SHIFT + ALT + D",
  "theme_path": "docker/omarchy-docker-theme.json",
  "max_rows": 40
}
```

Override the config location with `omarchy-docker --config <path> list`.

## Development

```bash
make check     # policy + unit + regression (fast)
make test      # full suite incl. measured mutation testing
SKIP_MUTATION=1 tools/run_tests.sh   # everything but mutation
```

Every test kind is present: unit, regression, integration, e2e and shell, plus
policy-as-code and a **measured** mutation score. No test needs a reachable Docker
daemon: unit and integration tests inject/mock the `docker` CLI, and the e2e test
puts a fake `docker` (and `getent`) on `PATH` to prove the real argument
construction. See `docs/` for the design and the verification notes.
