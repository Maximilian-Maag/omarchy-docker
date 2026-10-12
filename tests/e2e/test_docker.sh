#!/bin/bash
# e2e: drive the real CLI end-to-end with a fake `docker` (and `getent`) on PATH
# and assert the exact argument construction. No real daemon, and no container
# that belongs to the user, is ever touched.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLI="$ROOT/bin/omarchy-docker"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

export HOME="$WORK/home"
export XDG_STATE_HOME="$WORK/state"
export XDG_CONFIG_HOME="$WORK/config"
mkdir -p "$HOME"
mkdir -p "$XDG_STATE_HOME/omarchy/current/theme"
cat > "$XDG_STATE_HOME/omarchy/current/theme/colors.toml" <<'TOML'
mode = "dark"
accent = "#82FB9C"
selection = "#1f253a"
muted = "#2d3450"
background = "#0B0C16"
foreground = "#ddf7ff"
TOML

BIN="$WORK/bin"; mkdir -p "$BIN"; export PATH="$BIN:$PATH"
export DOCKER_LOG="$WORK/docker.log"; : > "$DOCKER_LOG"
cat > "$BIN/docker" <<'DOCKER'
#!/bin/bash
printf '%s\n' "$*" >> "$DOCKER_LOG"
case "${1:-}" in
  info)  exit "${FAKE_INFO_RC:-0}" ;;
  ps)    printf '%s' "${FAKE_PS:-}"; exit "${FAKE_PS_RC:-0}" ;;
  logs)  printf 'log line\n'; exit 0 ;;
  exec)  printf 'exec output\n'; exit 0 ;;
  *)     exit 0 ;;
esac
DOCKER
cat > "$BIN/getent" <<'GETENT'
#!/bin/bash
printf 'docker:x:966:mmaag\n'
exit 0
GETENT
chmod +x "$BIN/docker" "$BIN/getent"

fail=0
check() { if eval "$2"; then echo "e2e: ok — $1"; else echo "e2e: FAILED — $1" >&2; fail=1; fi; }

# --- status: in-group + reachable -------------------------------------------------
out="$("$CLI" status)"
check "status names the plugin"    "grep -q 'Maximilian-Maag.docker' <<<\"\$out\""
check "status reports reachable"   "grep -q 'daemon        : reachable' <<<\"\$out\""
check "status reports gid 966"     "grep -q 'docker group  : gid 966' <<<\"\$out\""

# --- status: unreachable prints the fix -------------------------------------------
out="$(FAKE_INFO_RC=1 "$CLI" status)"
check "status reports unreachable" "grep -q 'unreachable' <<<\"\$out\""

# --- list: real argv + themed-ready table -----------------------------------------
export FAKE_PS='{"Names":"web","Image":"nginx:1.27","State":"running","Status":"Up 2 hours"}
{"Names":"db","Image":"postgres:16","State":"exited","Status":"Exited (0) 3 days ago"}'
out="$("$CLI" list)"
check "list built the ps argv with json formatting" "grep -qF 'ps -a --format {{json .}}' \"\$DOCKER_LOG\""
check "list shows the container"                    "grep -q 'web' <<<\"\$out\""
check "list shows the image"                        "grep -q 'nginx:1.27' <<<\"\$out\""
check "list shows the stopped container"            "grep -q 'db' <<<\"\$out\""

# --- lifecycle + exec: exact argv --------------------------------------------------
: > "$DOCKER_LOG"
"$CLI" start web >/dev/null
"$CLI" stop db >/dev/null
"$CLI" restart db >/dev/null
"$CLI" logs web --tail 25 >/dev/null
"$CLI" exec web -- env >/dev/null
check "start argv"     "grep -qx 'start web' \"\$DOCKER_LOG\""
check "stop argv"      "grep -qx 'stop db' \"\$DOCKER_LOG\""
check "restart argv"   "grep -qx 'restart db' \"\$DOCKER_LOG\""
check "logs tail argv" "grep -qx 'logs --tail 25 web' \"\$DOCKER_LOG\""
check "exec argv"      "grep -qx 'exec web env' \"\$DOCKER_LOG\""

# --- theme: reads the applied theme live -------------------------------------------
"$CLI" theme >/dev/null
THEME_FILE="$XDG_CONFIG_HOME/docker/omarchy-docker-theme.json"
check "theme file written"     "[[ -f \"\$THEME_FILE\" ]]"
check "theme file has accent"  "grep -q '82FB9C' \"\$THEME_FILE\""

echo
if (( fail == 0 )); then echo "e2e: all checks passed"; exit 0; else echo "e2e: FAILED"; exit 1; fi
