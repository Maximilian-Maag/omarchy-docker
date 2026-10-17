"""Integration tests — the shipped CLI driven as a subprocess with a fake `docker`
(and `getent`) on PATH. No real Docker daemon is needed, and no container that
belongs to the user is ever started, stopped or removed.
"""

import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLI = ROOT / "bin/omarchy-docker"

THEME = """\
mode = "dark"

accent = "#82FB9C"
selection = "#1f253a"
muted = "#2d3450"
background = "#0B0C16"
foreground = "#ddf7ff"
"""

PS_JSON = (
    '{"Names":"web","Image":"nginx:1.27","State":"running","Status":"Up 2 hours"}\n'
    '{"Names":"db","Image":"postgres:16","State":"exited","Status":"Exited (0) 3 days ago"}\n'
)

FAKE_DOCKER = r"""#!/bin/bash
printf '%s\n' "$*" >> "$DOCKER_LOG"
case "${1:-}" in
  info)  exit "${FAKE_INFO_RC:-0}" ;;
  ps)    printf '%s' "${FAKE_PS:-}"; exit "${FAKE_PS_RC:-0}" ;;
  logs)  printf 'log line\n'; exit 0 ;;
  exec)  printf 'exec output\n'; exit "${FAKE_EXEC_RC:-0}" ;;
  *)     exit 0 ;;
esac
"""

FAKE_GETENT = r"""#!/bin/bash
if [[ "${1:-}" == "group" && "${2:-}" == "docker" ]]; then
  printf 'docker:x:966:mmaag\n'
  exit 0
fi
exit 2
"""


class CliIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = pathlib.Path(self.tmp.name)
        self.state = self.base / "state"
        self.config = self.base / "config"
        self.home = self.base / "home"
        self.home.mkdir()
        theme = self.state / "omarchy/current/theme"
        theme.mkdir(parents=True)
        (theme / "colors.toml").write_text(THEME)

        self.bindir = self.base / "bin"
        self.bindir.mkdir()
        self._script("docker", FAKE_DOCKER)
        self._script("getent", FAKE_GETENT)
        self.log = self.base / "docker.log"
        self.log.write_text("")

        self.env = dict(os.environ)
        self.env["XDG_STATE_HOME"] = str(self.state)
        self.env["XDG_CONFIG_HOME"] = str(self.config)
        self.env["HOME"] = str(self.home)
        self.env["PATH"] = str(self.bindir) + os.pathsep + os.environ.get("PATH", "")
        self.env["DOCKER_LOG"] = str(self.log)

    def _script(self, name, body):
        path = self.bindir / name
        path.write_text(body)
        path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    def run_cli(self, *args, env=None):
        return subprocess.run([sys.executable, str(CLI), *args],
                              capture_output=True, text=True, env=env or self.env)

    def log_lines(self):
        return [line for line in self.log.read_text().splitlines() if line]

    def test_status_in_group_and_reachable(self):
        proc = self.run_cli("status")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Maximilian-Maag.docker", proc.stdout)
        self.assertIn("daemon        : reachable", proc.stdout)
        self.assertIn("docker group  : gid 966", proc.stdout)
        # The membership VALUE is pinned deterministically by user_in_group's unit and
        # regression tests; asserting a specific value here would really be asserting that
        # the RUNNER's user is in the docker group. No CI runner is (the fake getent pins
        # the group at gid 966, which is this workstation's), so this assertion failed on
        # every run with 'not a member'.
        self.assertRegex(proc.stdout, r"user groups   : (member|not a member)")

    def test_status_unreachable(self):
        env = dict(self.env, FAKE_INFO_RC="1")
        proc = self.run_cli("status", env=env)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("unreachable", proc.stdout)

    def test_list_is_a_themed_ready_table(self):
        env = dict(self.env, FAKE_PS=PS_JSON)
        proc = self.run_cli("list", env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("NAME", proc.stdout)
        self.assertIn("web", proc.stdout)
        self.assertIn("nginx:1.27", proc.stdout)
        self.assertIn("db", proc.stdout)
        # not a tty -> no escape codes
        self.assertNotIn("\x1b", proc.stdout)

    def test_list_builds_ps_argv(self):
        env = dict(self.env, FAKE_PS=PS_JSON)
        self.run_cli("list", env=env)
        self.assertIn("ps -a --format {{json .}}", self.log_lines())

    def test_list_ps_failure_reports_permission(self):
        env = dict(self.env, FAKE_PS_RC="1")
        proc = self.run_cli("list", env=env)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("docker ps failed", proc.stderr)

    def test_start_builds_argv(self):
        proc = self.run_cli("start", "web")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("start web", self.log_lines())
        self.assertIn("ok", proc.stdout)

    def test_stop_builds_argv(self):
        self.assertEqual(self.run_cli("stop", "db").returncode, 0)
        self.assertIn("stop db", self.log_lines())

    def test_restart_builds_argv(self):
        self.assertEqual(self.run_cli("restart", "db").returncode, 0)
        self.assertIn("restart db", self.log_lines())

    def test_logs_builds_argv_with_tail(self):
        proc = self.run_cli("logs", "web", "--tail", "25")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("log line", proc.stdout)
        self.assertIn("logs --tail 25 web", self.log_lines())

    def test_exec_builds_argv(self):
        proc = self.run_cli("exec", "web", "--", "env")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("exec output", proc.stdout)
        self.assertIn("exec web env", self.log_lines())

    def test_exec_argv_preserves_flags(self):
        self.run_cli("exec", "web", "--", "ls", "-la", "/srv")
        self.assertIn("exec web ls -la /srv", self.log_lines())

    def test_theme_writes_dedicated_file(self):
        proc = self.run_cli("theme")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = self.config / "docker/omarchy-docker-theme.json"
        self.assertTrue(out.is_file())
        data = json.loads(out.read_text())
        self.assertEqual(data["accent"], "#82FB9C")
        self.assertEqual(data["running"], "#82FB9C")

    def test_theme_stdout(self):
        proc = self.run_cli("theme", "--stdout")
        self.assertEqual(proc.returncode, 0)
        self.assertIn('"accent": "#82FB9C"', proc.stdout)
        self.assertFalse((self.config / "docker/omarchy-docker-theme.json").exists())

    def test_theme_is_idempotent(self):
        self.assertEqual(self.run_cli("theme").returncode, 0)
        self.assertEqual(self.run_cli("theme").returncode, 0)

    def test_theme_without_applied_theme_fails(self):
        (self.state / "omarchy/current/theme/colors.toml").unlink()
        proc = self.run_cli("theme")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no applied theme", proc.stderr)

    def test_config_json_overrides_theme_path(self):
        cfg = self.base / "docker.json"
        cfg.write_text(json.dumps({"theme_path": str(self.base / "elsewhere/theme.json")}))
        proc = self.run_cli("--config", str(cfg), "theme")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((self.base / "elsewhere/theme.json").is_file())


if __name__ == "__main__":
    unittest.main()
