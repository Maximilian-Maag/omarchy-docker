# Verification notes

What was actually run and observed while building this plugin, plus what could
not be verified. Every command below was run from inside the repository.

## Machine

- Arch Linux, Hyprland/Omarchy, user `mmaag`.
- `docker` at `/usr/bin/docker`; `systemctl is-active docker` → **active**;
  `docker version` server → **29.7.2**.
- `getent group docker` → `docker:x:966:mmaag`; `id` →
  `uid=1000(mmaag) gid=1000(mmaag) groups=1000(mmaag),966(docker),998(wheel)`.
  The user **is** in the docker group, so the daemon is reachable.
- Applied theme: **Hackerman** (`omarchy theme current`), read live from
  `~/.local/state/omarchy/current/theme/colors.toml`
  (`accent = #82FB9C`, `background = #0B0C16`, `selection = #1f253a`,
  `muted = #2d3450`, `foreground = #ddf7ff`, `green = #4fe88f`, `red = #50f872`).

## The plugin on the real machine (read-only)

`python3 bin/omarchy-docker status`:

```
omarchy-docker Maximilian-Maag.docker
daemon        : reachable
docker group  : gid 966
user groups   : member
theme         : hackerman
```

`python3 bin/omarchy-docker list --no-color` renders the live container table
(NAME / IMAGE / STATE / STATUS) for the ten containers already on the machine.
Both commands are read-only; **no container belonging to the user was started,
stopped, restarted or removed** during this build.

## Test suite

Run with `tools/run_tests.sh` (or `make test`). Kinds and observed counts:

| kind        | command                                                       | result |
|-------------|---------------------------------------------------------------|--------|
| policy      | `python3 tools/policy_check.py`                               | 25 files, **0 failed, 0 warnings** |
| unit        | `python3 -m unittest discover -s tests -p 'test_unit_*.py'`   | **132 passed** |
| regression  | `python3 -m unittest discover -s tests -p 'test_regression_*.py'` | **18 passed** |
| integration | `python3 -m unittest discover -s tests -p 'test_integration_*.py'` | **16 passed** |
| e2e         | `bash tests/e2e/test_docker.sh`                               | **15 checks passed** |
| shell       | `bash tests/shell/test_*.sh`                                  | **17 passed** (11 hook + 6 install) |
| mutation    | `python3 tools/mutator.py`                                    | **45/45 + 5/5 killed, rate 1.00** (> 0.80) |

No test needs a reachable Docker daemon: unit tests replace `default_runner`
(the injectable seam), integration and e2e tests put a fake `docker` (and
`getent`) on `PATH`.

## Hook and keybinding

- The `theme-set` hook is shipped as `hooks/docker-theme-set` and installed under
  that unique basename (the basename-clobber hazard). It self-locates via
  `$OMARCHY_DOCKER_DIR` → the Omarchy plugins dir → the dev checkout, because an
  installed hook copied into the hooks dir cannot find its plugin via
  `$(dirname "$BASH_SOURCE")/..`.
- The hook is exercised hermetically in `tests/shell/test_theme_set.sh` with a
  throwaway `HOME`/XDG: generation, the empty-name no-op, a missing plugin, the
  self-location fallback and a failing CLI.

## What was NOT verified

- The Hyprland keybinding was **not** loaded into a live compositor during this
  build: that requires editing `~/.config/hypr/hyprland.lua` and reloading the
  user's session, which is left to the user. Its shape (`hl.unbind` + `o.bind` +
  `xdg-terminal-exec … omarchy-docker list`) is pinned by the regression suite and
  installed into a throwaway `XDG_CONFIG_HOME` by `tests/shell/test_install.sh`.
- The installed `theme-set` hook was not registered with a real
  `omarchy hook install` (that mutates the user's `~/.config/omarchy/hooks`).
- The join-the-docker-group fix (`sudo usermod -aG docker $USER`) was not applied
  — this build does not change group membership; on this machine it is not even
  needed, since `mmaag` is already a member.

## Mutation

`tests/mutation.json` uses `per_operator: 6` and `max_mutants: 220`. Two targets
(`bin/omarchy-docker` python, `hooks/docker-theme-set` shell); `bin/bindings.lua`
and the two vendored `tools/*.py` are exempt with stated reasons. The measured
run kills every counted mutant. No `equivalent` entries were needed, so none is
asserted.
