# Design

`omarchy-docker` is a **CLI + hyprland-module** Omarchy plugin (the non-QML kind).
It ships a Python CLI (`bin/omarchy-docker`), a Hyprland keybinding module
(`bin/bindings.lua`), a uniquely-named `theme-set` hook
(`hooks/docker-theme-set`) and a small config (`config/docker.json`).

## Layering

```
bin/omarchy-docker        the CLI (all logic lives here, dependency-free)
bin/bindings.lua          Hyprland keybinding -> `omarchy-docker list` in a floating terminal
hooks/docker-theme-set    theme-set hook: regenerate the colour roles
config/docker.json        keybinding, theme file path, listing row cap
```

## The single seam to the outside world

Every interaction with the `docker` binary goes through one function:

```python
def default_runner(argv):        # (returncode, stdout, stderr)
    ...
def system(argv, runner=None):   # run any argv through the seam
def docker(args, runner=None):   # system(["docker", *args], runner)
```

Tests replace `default_runner` (unit tests) or put a fake `docker` on `PATH`
(integration / e2e tests). Nothing in the test suite needs a reachable Docker
daemon, and no test ever starts, stops or removes a container that belongs to the
user.

`status` additionally reads the docker group's gid with `getent group docker`
through the same seam, so a fake `getent` can be injected for deterministic tests.

## Theme handling (no baked palette)

The applied theme is a *copy* at
`~/.local/state/omarchy/current/theme/colors.toml`; its directory is always
literally `theme`, so the theme's name is not in the path. `status` recovers the
name by matching the colour set against every installed theme directory, rather
than assuming a default. The CLI carries **no hex literal of its own** — a
regression test asserts this by scanning the source for `#rrggbb` patterns.

`build_theme()` maps Omarchy colour keys to the container view's roles:

| view role     | Omarchy keys (in order of preference)                    |
|---------------|----------------------------------------------------------|
| `background`  | `background`, `base`                                     |
| `foreground`  | `foreground`, `text`                                     |
| `accent`      | `accent`, `blue`                                         |
| `muted`       | `muted`, `dark_foreground`, `foreground`, `text`         |
| `selection`   | `selection`, `lighter_background`, `background`, `base`  |
| `running`     | `green`, `accent`, `blue`                                |
| `stopped`     | `red`, `muted`, `dark_foreground`, `foreground`, `text`  |

A Hyprland gradient stop such as `rgba(26a269ee)` is reduced to its `#rrggbb`
before being turned into a 24-bit ANSI escape (true colour).

## Docker group honesty

`user_in_group(gid, gids)` compares the *actual* gid of the `docker` group against
the *actual* group ids of the process. When neither the daemon is reachable nor
the user is a member, `status` prints the exact remediation
(`sudo usermod -aG docker $USER`, then re-login) instead of pretending it works.
The plugin never calls `usermod` itself: joining the `docker` group is equivalent
to passwordless root.

## Hook basename hazard

`omarchy hook install theme-set <file>` installs the hook under the file's
**basename**, so a file literally named `theme-set` clobbers every other plugin's
theme-set hook. This plugin ships `hooks/docker-theme-set` and `install.sh`
installs it under that name. Because the installed hook sits in the hooks dir,
`$(dirname "$BASH_SOURCE")/..` does **not** reach the plugin; the hook self-locates
via `$OMARCHY_DOCKER_DIR`, the Omarchy plugins dir, then the dev checkout.
