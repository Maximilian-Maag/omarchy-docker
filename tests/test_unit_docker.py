"""Unit tests for omarchy-docker's pure logic.

The shipped CLI has no ``.py`` extension (it is installed as ``omarchy-docker``),
so it is loaded with a SourceFileLoader rather than imported by name. Every docker
call goes through the injectable runner seam, so nothing here needs a daemon.
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLI = ROOT / "bin/omarchy-docker"

_loader = importlib.machinery.SourceFileLoader("omarchy_docker", str(CLI))
_spec = importlib.util.spec_from_loader("omarchy_docker", _loader)
dock = importlib.util.module_from_spec(_spec)
_loader.exec_module(dock)

SAMPLE = """\
mode = "dark"

# the accent
accent = "#82FB9C"
selection = "#1f253a"
muted = "#2d3450"

background = "#0B0C16"
foreground = "#ddf7ff"
hyprland_active_border = "rgba(26a269ee) rgba(2ec27eee) 45deg"
"""

COLORS = {
    "mode": "dark",
    "accent": "#82FB9C",
    "selection": "#1f253a",
    "muted": "#2d3450",
    "background": "#0B0C16",
    "foreground": "#ddf7ff",
}

THEME = {
    "background": "#0B0C16",
    "foreground": "#ddf7ff",
    "accent": "#82FB9C",
    "muted": "#2d3450",
    "selection": "#1f253a",
    "running": "#82FB9C",
    "stopped": "#ff5555",
}

PS_JSON = (
    '{"Names":"web","Image":"nginx:1.27","State":"running","Status":"Up 2 hours"}\n'
    '{"Names":"db","Image":"postgres:16","State":"exited","Status":"Exited (0) 3 days ago"}\n'
)


class FakeRunner:
    """A stand-in for the docker/getent seam: records argv, returns canned data."""

    def __init__(self):
        self.calls = []
        self.rules = []

    def on(self, prefix, rc=0, out="", err=""):
        self.rules.append((prefix, (rc, out, err)))
        return self

    def __call__(self, argv):
        self.calls.append(list(argv))
        key = " ".join(argv)
        for prefix, result in self.rules:
            if key == prefix or key.startswith(prefix):
                return result
        return 0, "", ""

    def argv_for(self, first):
        for call in self.calls:
            if call and call[0] == first:
                return call
        return None


def run_main(argv, runner=None):
    """Run the CLI in-process, returning (rc, combined output)."""
    old = dock.default_runner
    if runner is not None:
        dock.default_runner = runner
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = dock.main(list(argv))
    finally:
        dock.default_runner = old
    return rc, buf.getvalue()


class ParseColors(unittest.TestCase):
    def test_basic_keys_and_values(self):
        colors = dock.parse_colors(SAMPLE)
        self.assertEqual(colors["accent"], "#82FB9C")
        self.assertEqual(colors["background"], "#0B0C16")
        self.assertEqual(colors["mode"], "dark")

    def test_comments_and_blanks_skipped(self):
        colors = dock.parse_colors("# a comment\n\n   \naccent = \"#fff\"\n")
        self.assertEqual(colors, {"accent": "#fff"})

    def test_comment_containing_equals_is_not_parsed(self):
        colors = dock.parse_colors('# accent = "#fff"\naccent = "#000"\n')
        self.assertEqual(colors, {"accent": "#000"})

    def test_hex_colour_is_not_treated_as_a_comment(self):
        self.assertEqual(dock.parse_colors('accent = "#82FB9C"\n')["accent"], "#82FB9C")

    def test_line_without_equals_is_skipped(self):
        self.assertEqual(dock.parse_colors('garbage\naccent = "#fff"\n'), {"accent": "#fff"})

    def test_empty_key_is_skipped(self):
        self.assertEqual(dock.parse_colors('= nope\naccent = "#fff"\n'), {"accent": "#fff"})

    def test_single_quotes_stripped(self):
        self.assertEqual(dock.parse_colors("accent = '#fff'\n")["accent"], "#fff")

    def test_unquoted_value_kept(self):
        self.assertEqual(dock.parse_colors("mode = dark\n")["mode"], "dark")


class NormalizeHex(unittest.TestCase):
    def test_hex_passthrough(self):
        self.assertEqual(dock.normalize_hex("#82FB9C"), "#82FB9C")

    def test_rgba_reduced_to_hex(self):
        self.assertEqual(dock.normalize_hex("rgba(26a269ee)"), "#26a269")

    def test_rgba_with_alpha_zero(self):
        self.assertEqual(dock.normalize_hex("rgba(2ec27e00)"), "#2ec27e")

    def test_short_hex_rejected(self):
        with self.assertRaises(ValueError):
            dock.normalize_hex("#fff")

    def test_garbage_rejected(self):
        with self.assertRaises(ValueError):
            dock.normalize_hex("not-a-colour")

    def test_whitespace_stripped(self):
        self.assertEqual(dock.normalize_hex("  #82FB9C  "), "#82FB9C")


class RgbAndAnsi(unittest.TestCase):
    def test_hex_to_rgb(self):
        self.assertEqual(dock.hex_to_rgb("#82FB9C"), (130, 251, 156))

    def test_hex_to_rgb_black(self):
        self.assertEqual(dock.hex_to_rgb("#000000"), (0, 0, 0))

    def test_hex_to_rgb_white(self):
        self.assertEqual(dock.hex_to_rgb("#ffffff"), (255, 255, 255))

    def test_hex_to_rgb_accepts_rgba(self):
        self.assertEqual(dock.hex_to_rgb("rgba(26a269ff)"), (38, 162, 105))

    def test_ansi_fg(self):
        self.assertEqual(dock.ansi_fg("#82FB9C"), "\x1b[38;2;130;251;156m")

    def test_ansi_bg(self):
        self.assertEqual(dock.ansi_bg("#0B0C16"), "\x1b[48;2;11;12;22m")


class NormalizeName(unittest.TestCase):
    def test_title_case_to_slug(self):
        self.assertEqual(dock.normalize_name("Tokyo Night"), "tokyo-night")

    def test_strips_and_lowercases(self):
        self.assertEqual(dock.normalize_name("  Hackerman  "), "hackerman")


class ResolveThemeName(unittest.TestCase):
    def _theme(self, root, name, body):
        d = root / name
        d.mkdir()
        (d / "colors.toml").write_text(body)
        return d

    def test_matches_colour_set(self):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            self._theme(root, "nord", 'accent = "#88c0d0"\nbackground = "#2e3440"\n')
            self._theme(root, "gruvbox", 'accent = "#d79921"\nbackground = "#282828"\n')
            colors = {"accent": "#d79921", "background": "#282828"}
            self.assertEqual(
                dock.resolve_theme_name(colors, [root / "nord", root / "gruvbox"]), "gruvbox")

    def test_no_match_returns_empty(self):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            self._theme(root, "nord", 'accent = "#88c0d0"\n')
            self.assertEqual(dock.resolve_theme_name({"accent": "#000000"}, [root / "nord"]), "")

    def test_missing_colors_file_skipped(self):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            (root / "empty").mkdir()
            self.assertEqual(dock.resolve_theme_name({"a": "b"}, [root / "empty"]), "")


class FirstAndBuildTheme(unittest.TestCase):
    def test_first_returns_present(self):
        self.assertEqual(dock._first({"a": "1", "b": "2"}, "b", "a"), "2")

    def test_first_skips_empty(self):
        self.assertEqual(dock._first({"a": "", "b": "2"}, "a", "b"), "2")

    def test_first_raises_when_absent(self):
        with self.assertRaises(ValueError):
            dock._first({"a": "1"}, "x", "y")

    def test_build_theme_uses_theme_colours(self):
        theme = dock.build_theme(dict(COLORS))
        self.assertEqual(theme["background"], "#0B0C16")
        self.assertEqual(theme["foreground"], "#ddf7ff")
        self.assertEqual(theme["accent"], "#82FB9C")
        self.assertEqual(theme["selection"], "#1f253a")
        self.assertEqual(theme["muted"], "#2d3450")

    def test_running_falls_back_to_accent(self):
        self.assertEqual(dock.build_theme(dict(COLORS))["running"], "#82FB9C")

    def test_running_uses_green_when_present(self):
        colors = dict(COLORS, green="#00ff00")
        self.assertEqual(dock.build_theme(colors)["running"], "#00ff00")

    def test_stopped_uses_red_when_present(self):
        colors = dict(COLORS, red="#ff0000")
        self.assertEqual(dock.build_theme(colors)["stopped"], "#ff0000")

    def test_stopped_falls_back_to_muted(self):
        self.assertEqual(dock.build_theme(dict(COLORS))["stopped"], "#2d3450")

    def test_muted_falls_back_to_dark_foreground(self):
        colors = {k: v for k, v in COLORS.items() if k != "muted"}
        colors["dark_foreground"] = "#6a6e95"
        self.assertEqual(dock.build_theme(colors)["muted"], "#6a6e95")

    def test_selection_falls_back_to_lighter_background(self):
        colors = {k: v for k, v in COLORS.items() if k != "selection"}
        colors["lighter_background"] = "#151828"
        self.assertEqual(dock.build_theme(colors)["selection"], "#151828")

    def test_selection_falls_back_to_background(self):
        colors = {k: v for k, v in COLORS.items() if k != "selection"}
        self.assertEqual(dock.build_theme(colors)["selection"], "#0B0C16")

    def test_missing_background_raises(self):
        colors = {k: v for k, v in COLORS.items() if k != "background"}
        with self.assertRaises(ValueError):
            dock.build_theme(colors)

    def test_gradient_accent_accepted(self):
        colors = dict(COLORS, accent="rgba(26a269ee)")
        self.assertEqual(dock.build_theme(colors)["accent"], "#26a269")


class DockerGroup(unittest.TestCase):
    def test_parses_gid(self):
        self.assertEqual(dock.docker_group_gid("docker:x:966:mmaag\n"), 966)

    def test_other_group_is_none(self):
        self.assertIsNone(dock.docker_group_gid("users:x:100:mmaag\n"))

    def test_short_line_is_none(self):
        self.assertIsNone(dock.docker_group_gid("docker:x\n"))

    def test_non_numeric_gid_is_none(self):
        self.assertIsNone(dock.docker_group_gid("docker:x:abc:mmaag\n"))

    def test_empty_is_none(self):
        self.assertIsNone(dock.docker_group_gid(""))

    def test_lookup_parses(self):
        runner = FakeRunner().on("getent group docker", 0, "docker:x:966:mmaag\n")
        self.assertEqual(dock.lookup_docker_gid(runner), 966)

    def test_lookup_missing_group(self):
        runner = FakeRunner().on("getent group docker", 2, "", "")
        self.assertIsNone(dock.lookup_docker_gid(runner))


class UserInGroup(unittest.TestCase):
    def test_member(self):
        self.assertTrue(dock.user_in_group(966, {1000, 966}))

    def test_not_member(self):
        self.assertFalse(dock.user_in_group(966, {1000, 998}))

    def test_no_group(self):
        self.assertFalse(dock.user_in_group(None, {1000, 966}))

    def test_current_group_ids_is_a_set(self):
        self.assertIsInstance(dock.current_group_ids(), set)


class FakeRunnerSeam(unittest.TestCase):
    def test_docker_prefixes_argv(self):
        runner = FakeRunner()
        dock.docker(["ps"], runner)
        self.assertEqual(runner.calls[0], ["docker", "ps"])

    def test_system_runs_raw_argv(self):
        runner = FakeRunner()
        dock.system(["getent", "group", "docker"], runner)
        self.assertEqual(runner.calls[0], ["getent", "group", "docker"])

    def test_default_runner_used_when_none(self):
        runner = FakeRunner()
        dock.default_runner = runner
        try:
            dock.docker(["info"])
        finally:
            dock.default_runner = _loader_runner[0]
        self.assertEqual(runner.calls[0], ["docker", "info"])

    def test_default_runner_reports_launch_failure(self):
        rc, out, err = dock.default_runner(["/nonexistent-omarchy-docker-xyz"])
        self.assertEqual(rc, 127)
        self.assertIn("could not run", err)

    def test_default_runner_runs_true(self):
        rc, out, err = dock.default_runner(["true"])
        self.assertEqual(rc, 0)

    def test_default_runner_captures_stdout(self):
        rc, out, err = dock.default_runner(["echo", "hi"])
        self.assertEqual(out, "hi\n")

    def test_timeout_constant(self):
        self.assertEqual(dock.DEFAULT_TIMEOUT, 30)


_loader_runner = [dock.default_runner]


class DaemonReachable(unittest.TestCase):
    def test_reachable(self):
        runner = FakeRunner().on("docker info", 0, "Server Version: 29.7.2", "")
        self.assertEqual(dock.daemon_reachable(runner), (True, ""))

    def test_unreachable_with_stderr(self):
        runner = FakeRunner().on("docker info", 1, "", "Cannot connect to the Docker daemon")
        self.assertEqual(dock.daemon_reachable(runner),
                         (False, "Cannot connect to the Docker daemon"))

    def test_unreachable_uses_stdout_when_stderr_empty(self):
        runner = FakeRunner().on("docker info", 1, "permission denied", "")
        self.assertEqual(dock.daemon_reachable(runner), (False, "permission denied"))

    def test_unreachable_default_detail(self):
        runner = FakeRunner().on("docker info", 1, "", "")
        self.assertEqual(dock.daemon_reachable(runner), (False, "daemon not reachable"))


class ParsePs(unittest.TestCase):
    def test_parses_multiple(self):
        containers = dock.parse_ps(PS_JSON)
        self.assertEqual([c["Names"] for c in containers], ["web", "db"])

    def test_skips_blank_lines(self):
        self.assertEqual(len(dock.parse_ps("\n" + PS_JSON + "\n\n")), 2)

    def test_skips_non_json_lines(self):
        self.assertEqual(len(dock.parse_ps("garbage\n" + PS_JSON)), 2)

    def test_skips_unparseable_json(self):
        self.assertEqual(len(dock.parse_ps('{"Names": \n' + PS_JSON)), 2)

    def test_skips_json_non_dict(self):
        self.assertEqual(len(dock.parse_ps("[1,2,3]\n" + PS_JSON)), 2)

    def test_empty(self):
        self.assertEqual(dock.parse_ps(""), [])


class ContainerState(unittest.TestCase):
    def test_state_field(self):
        self.assertEqual(dock.container_state({"State": "running"}), "running")

    def test_state_lowercased(self):
        self.assertEqual(dock.container_state({"State": "Running"}), "running")

    def test_status_up_means_running(self):
        self.assertEqual(dock.container_state({"Status": "Up 2 hours"}), "running")

    def test_status_exited(self):
        self.assertEqual(dock.container_state({"Status": "Exited (0) 3 days ago"}), "exited")

    def test_unknown(self):
        self.assertEqual(dock.container_state({"Status": "Created"}), "unknown")

    def test_is_running(self):
        self.assertTrue(dock.is_running({"State": "running"}))
        self.assertFalse(dock.is_running({"State": "exited"}))

    def test_name(self):
        self.assertEqual(dock.container_name({"Names": "web"}), "web")

    def test_name_fallback(self):
        self.assertEqual(dock.container_name({"Name": "db"}), "db")

    def test_name_empty(self):
        self.assertEqual(dock.container_name({}), "")


class VisibleRows(unittest.TestCase):
    ROWS = [{"Names": "a"}, {"Names": "b"}, {"Names": "c"}]

    def test_cap(self):
        self.assertEqual(len(dock.visible_rows(self.ROWS, 2)), 2)

    def test_cap_one(self):
        self.assertEqual([c["Names"] for c in dock.visible_rows(self.ROWS, 1)], ["a"])

    def test_zero_means_all(self):
        self.assertEqual(len(dock.visible_rows(self.ROWS, 0)), 3)

    def test_none_means_all(self):
        self.assertEqual(len(dock.visible_rows(self.ROWS, None)), 3)


class Pad(unittest.TestCase):
    def test_pads(self):
        self.assertEqual(dock.pad("ab", 4), "ab  ")

    def test_exact(self):
        self.assertEqual(dock.pad("abcd", 4), "abcd")

    def test_longer_untouched(self):
        self.assertEqual(dock.pad("abcde", 4), "abcde")


class StateColour(unittest.TestCase):
    def test_running(self):
        self.assertEqual(dock.state_colour("running", THEME), THEME["running"])

    def test_exited(self):
        self.assertEqual(dock.state_colour("exited", THEME), THEME["stopped"])

    def test_dead(self):
        self.assertEqual(dock.state_colour("dead", THEME), THEME["stopped"])

    def test_other(self):
        self.assertEqual(dock.state_colour("created", THEME), THEME["muted"])


class RenderTable(unittest.TestCase):
    CONTAINERS = dock.parse_ps(PS_JSON)

    def test_contains_headers_and_names(self):
        table = dock.render_table(self.CONTAINERS, THEME, color=False)
        self.assertIn("NAME", table)
        self.assertIn("IMAGE", table)
        self.assertIn("STATUS", table)
        self.assertIn("web", table)
        self.assertIn("nginx:1.27", table)
        self.assertIn("db", table)

    def test_no_colour_has_no_escape(self):
        table = dock.render_table(self.CONTAINERS, THEME, color=False)
        self.assertNotIn("\x1b", table)

    def test_colour_paints_rows(self):
        table = dock.render_table(self.CONTAINERS, THEME, color=True)
        self.assertIn(dock.ansi_fg(THEME["running"]), table)
        self.assertIn(dock.ansi_fg(THEME["stopped"]), table)

    def test_columns_aligned(self):
        table = dock.render_table(self.CONTAINERS, THEME, color=False)
        lines = table.splitlines()
        positions = [lines[0].index("IMAGE"), lines[0].index("STATE"), lines[0].index("STATUS")]
        for line in lines[1:]:
            for pos in positions:
                self.assertEqual(line[pos - 2:pos], "  ")

    def test_empty_is_header_only(self):
        table = dock.render_table([], THEME, color=False)
        self.assertEqual(len(table.splitlines()), 1)

    def test_ends_with_newline(self):
        self.assertTrue(dock.render_table(self.CONTAINERS, THEME, color=False).endswith("\n"))

    def test_default_color_is_on(self):
        table = dock.render_table(self.CONTAINERS, THEME)
        self.assertIn("\x1b", table)


class RenderStatus(unittest.TestCase):
    def test_reachable_member(self):
        text = dock.render_status({"reachable": True, "group_gid": 966, "in_group": True,
                                   "theme": "Hackerman"})
        self.assertIn("reachable", text)
        self.assertIn("member", text)
        self.assertIn("gid 966", text)
        self.assertIn("Hackerman", text)
        self.assertNotIn("fix", text)

    def test_unreachable_not_member_prints_fix(self):
        text = dock.render_status({"reachable": False, "detail": "permission denied",
                                   "group_gid": 966, "in_group": False, "theme": ""})
        self.assertIn("unreachable", text)
        self.assertIn("permission denied", text)
        self.assertIn("not a member", text)
        self.assertIn("usermod -aG docker", text)
        self.assertIn("(unknown)", text)

    def test_unreachable_but_member_no_fix(self):
        text = dock.render_status({"reachable": False, "group_gid": 966, "in_group": True,
                                   "theme": ""})
        self.assertNotIn("usermod -aG docker", text)

    def test_group_absent(self):
        text = dock.render_status({"reachable": True, "group_gid": None, "in_group": False,
                                   "theme": ""})
        self.assertIn("not present", text)

    def test_includes_plugin_id(self):
        text = dock.render_status({"reachable": True, "group_gid": 1, "in_group": True,
                                   "theme": ""})
        self.assertIn("Maximilian-Maag.docker", text)


class ConfigAndPaths(unittest.TestCase):
    def test_default_theme_path(self):
        self.assertEqual(dock.theme_path({}),
                         dock.config_home() / "docker/omarchy-docker-theme.json")

    def test_theme_path_override_tilde(self):
        cfg = {"theme_path": "~/.config/docker/custom.json"}
        self.assertEqual(dock.theme_path(cfg),
                         pathlib.Path(os.path.expanduser("~/.config/docker/custom.json")))

    def test_theme_path_override_absolute(self):
        cfg = {"theme_path": "/tmp/omarchy-docker-test/theme.json"}
        self.assertEqual(dock.theme_path(cfg),
                         pathlib.Path("/tmp/omarchy-docker-test/theme.json"))

    def test_load_config_reads_file(self):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "docker.json"
            p.write_text(json.dumps({"keybinding": "SUPER + X"}))
            cfg = dock.load_config(p)
            self.assertEqual(cfg["keybinding"], "SUPER + X")
            self.assertIn("theme_path", cfg)

    def test_load_config_missing_uses_defaults(self):
        cfg = dock.load_config(pathlib.Path("/nonexistent/docker.json"))
        self.assertEqual(cfg["theme_path"], dock.DEFAULT_CONFIG["theme_path"])

    def test_load_config_invalid_json_uses_defaults(self):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "docker.json"
            p.write_text("{ not json")
            self.assertEqual(dock.load_config(p)["keybinding"],
                             dock.DEFAULT_CONFIG["keybinding"])

    def test_state_home_env(self):
        old = os.environ.get("XDG_STATE_HOME")
        os.environ["XDG_STATE_HOME"] = "/tmp/state-xyz"
        try:
            self.assertEqual(dock.state_home(), pathlib.Path("/tmp/state-xyz"))
        finally:
            os.environ.pop("XDG_STATE_HOME", None)
            if old is not None:
                os.environ["XDG_STATE_HOME"] = old

    def test_config_home_env(self):
        old = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = "/tmp/config-xyz"
        try:
            self.assertEqual(dock.config_home(), pathlib.Path("/tmp/config-xyz"))
        finally:
            os.environ.pop("XDG_CONFIG_HOME", None)
            if old is not None:
                os.environ["XDG_CONFIG_HOME"] = old

    def test_colors_path_under_state_home(self):
        old = os.environ.get("XDG_STATE_HOME")
        os.environ["XDG_STATE_HOME"] = "/tmp/state-xyz"
        try:
            self.assertEqual(dock.theme_colors_path(),
                             pathlib.Path("/tmp/state-xyz/omarchy/current/theme/colors.toml"))
        finally:
            os.environ.pop("XDG_STATE_HOME", None)
            if old is not None:
                os.environ["XDG_STATE_HOME"] = old

    def test_theme_search_dirs(self):
        with tempfile.TemporaryDirectory() as t:
            base = pathlib.Path(t)
            (base / "omarchy/themes/nord").mkdir(parents=True)
            old = os.environ.get("XDG_CONFIG_HOME")
            os.environ["XDG_CONFIG_HOME"] = str(base)
            try:
                dirs = dock.theme_search_dirs()
                self.assertIn(base / "omarchy/themes/nord", dirs)
            finally:
                if old is None:
                    os.environ.pop("XDG_CONFIG_HOME", None)
                else:
                    os.environ["XDG_CONFIG_HOME"] = old

    def test_plugin_dir_is_repo_root(self):
        self.assertEqual(dock.plugin_dir(), ROOT)

    def test_default_max_rows(self):
        self.assertEqual(dock.DEFAULT_CONFIG["max_rows"], 40)


class Commands(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = pathlib.Path(self.tmp.name)
        self.state = base / "state"
        self.config = base / "config"
        theme = self.state / "omarchy/current/theme"
        theme.mkdir(parents=True)
        (theme / "colors.toml").write_text(SAMPLE)
        self._env = {k: os.environ.get(k) for k in ("XDG_STATE_HOME", "XDG_CONFIG_HOME")}
        os.environ["XDG_STATE_HOME"] = str(self.state)
        os.environ["XDG_CONFIG_HOME"] = str(self.config)
        self.addCleanup(self._restore)

    def _restore(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _runner(self):
        return (FakeRunner()
                .on("docker info", 0, "")
                .on("docker ps", 0, PS_JSON)
                .on("getent group docker", 0, "docker:x:966:mmaag\n"))

    def test_status_runs(self):
        rc, out = run_main(["status"], self._runner())
        self.assertEqual(rc, 0)
        self.assertIn("Maximilian-Maag.docker", out)
        self.assertIn("daemon", out)
        self.assertIn("docker group", out)

    def test_status_unreachable_reports_it(self):
        runner = FakeRunner().on("docker info", 1, "", "Cannot connect to the Docker daemon")
        rc, out = run_main(["status"], runner)
        self.assertEqual(rc, 0)
        self.assertIn("unreachable", out)

    def test_list_plain_has_no_escape_codes(self):
        rc, out = run_main(["list"], self._runner())
        self.assertEqual(rc, 0)
        self.assertIn("web", out)
        self.assertIn("db", out)
        self.assertNotIn("\x1b[", out)

    def test_list_no_color_flag(self):
        rc, out = run_main(["list", "--no-color"], self._runner())
        self.assertEqual(rc, 0)
        self.assertNotIn("\x1b[", out)

    def test_list_empty(self):
        runner = (FakeRunner().on("docker ps", 0, "")
                  .on("getent group docker", 0, ""))
        rc, out = run_main(["list"], runner)
        self.assertEqual(rc, 0)
        self.assertIn("no containers", out)

    def test_list_without_theme_is_plain(self):
        (self.state / "omarchy/current/theme/colors.toml").unlink()
        runner = FakeRunner().on("docker ps", 0, PS_JSON)
        rc, out = run_main(["list"], runner)
        self.assertEqual(rc, 0)
        self.assertIn("web", out)
        self.assertNotIn("\x1b[", out)

    def test_list_ps_failure(self):
        runner = FakeRunner().on("docker ps", 1, "", "permission denied while trying to connect")
        rc, out = run_main(["list"], runner)
        self.assertEqual(rc, 1)
        self.assertIn("permission denied", out)

    def test_start_ok(self):
        runner = FakeRunner().on("docker start", 0, "web\n")
        rc, out = run_main(["start", "web"], runner)
        self.assertEqual(rc, 0)
        self.assertIn("start web: ok", out)
        self.assertEqual(runner.argv_for("docker"), ["docker", "start", "web"])

    def test_start_failure(self):
        runner = FakeRunner().on("docker start", 1, "", "no such container")
        rc, out = run_main(["start", "web"], runner)
        self.assertEqual(rc, 1)
        self.assertIn("no such container", out)

    def test_start_failure_without_message(self):
        runner = FakeRunner().on("docker start", 3, "", "")
        rc, out = run_main(["start", "web"], runner)
        self.assertEqual(rc, 1)
        self.assertIn("docker returned 3", out)

    def test_stop_arg(self):
        runner = FakeRunner()
        rc, out = run_main(["stop", "db"], runner)
        self.assertEqual(rc, 0)
        self.assertEqual(runner.argv_for("docker"), ["docker", "stop", "db"])

    def test_restart_arg(self):
        runner = FakeRunner()
        rc, out = run_main(["restart", "db"], runner)
        self.assertEqual(rc, 0)
        self.assertEqual(runner.argv_for("docker"), ["docker", "restart", "db"])

    def test_logs_arg(self):
        runner = FakeRunner().on("docker logs", 0, "line one\n", "")
        rc, out = run_main(["logs", "web"], runner)
        self.assertEqual(rc, 0)
        self.assertIn("line one", out)
        self.assertEqual(runner.argv_for("docker"), ["docker", "logs", "web"])

    def test_logs_tail_arg(self):
        runner = FakeRunner().on("docker logs", 0, "x\n", "")
        rc, out = run_main(["logs", "web", "--tail", "50"], runner)
        self.assertEqual(rc, 0)
        self.assertEqual(runner.argv_for("docker"), ["docker", "logs", "--tail", "50", "web"])

    def test_logs_failure_returns_1(self):
        runner = FakeRunner().on("docker logs", 1, "", "no such container")
        rc, out = run_main(["logs", "web"], runner)
        self.assertEqual(rc, 1)
        self.assertIn("no such container", out)

    def test_exec_strips_leading_dashdash(self):
        runner = FakeRunner().on("docker exec", 0, "ok\n", "")
        rc, out = run_main(["exec", "web", "--", "env"], runner)
        self.assertEqual(rc, 0)
        self.assertEqual(runner.argv_for("docker"), ["docker", "exec", "web", "env"])

    def test_exec_without_dashdash(self):
        runner = FakeRunner()
        rc, out = run_main(["exec", "web", "ls", "-la"], runner)
        self.assertEqual(rc, 0)
        self.assertEqual(runner.argv_for("docker"), ["docker", "exec", "web", "ls", "-la"])

    def test_exec_failure(self):
        runner = FakeRunner().on("docker exec", 1, "", "boom")
        rc, out = run_main(["exec", "web", "--", "false"], runner)
        self.assertEqual(rc, 1)
        self.assertIn("boom", out)

    def test_theme_writes_file(self):
        rc, out = run_main(["theme"])
        self.assertEqual(rc, 0)
        out_path = dock.theme_path()
        self.assertTrue(out_path.is_file())
        data = json.loads(out_path.read_text())
        self.assertEqual(data["accent"], "#82FB9C")
        self.assertEqual(out_path.read_text(), json.dumps(dock.build_theme(dict(COLORS)),
                                                          indent=2) + "\n")

    def test_theme_stdout_does_not_write(self):
        rc, out = run_main(["theme", "--stdout"])
        self.assertEqual(rc, 0)
        self.assertIn('"accent": "#82FB9C"', out)
        self.assertFalse(dock.theme_path().exists())

    def test_theme_missing_theme_returns_1(self):
        (self.state / "omarchy/current/theme/colors.toml").unlink()
        rc, out = run_main(["theme"])
        self.assertEqual(rc, 1)
        self.assertIn("no applied theme", out)

    def test_config_json_overrides_theme_path(self):
        cfg = pathlib.Path(self.tmp.name) / "docker.json"
        cfg.write_text(json.dumps({"theme_path": str(pathlib.Path(self.tmp.name) / "else/theme.json")}))
        rc, out = run_main(["--config", str(cfg), "theme"])
        self.assertEqual(rc, 0)
        self.assertTrue((pathlib.Path(self.tmp.name) / "else/theme.json").is_file())


if __name__ == "__main__":
    unittest.main()
