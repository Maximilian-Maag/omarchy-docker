"""Regression tests — one per real bug / design hazard this plugin must not regress.

Each test fails if the guard is removed, and names the hazard it pins.
"""

import importlib.machinery
import importlib.util
import json
import os
import pathlib
import re
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLI = ROOT / "bin/omarchy-docker"

_loader = importlib.machinery.SourceFileLoader("omarchy_docker_reg", str(CLI))
_spec = importlib.util.spec_from_loader("omarchy_docker_reg", _loader)
dock = importlib.util.module_from_spec(_spec)
_loader.exec_module(dock)


class HookFilenameHazard(unittest.TestCase):
    """HAZARD: `omarchy hook install theme-set <file>` installs the hook under
    its BASENAME, so a hook literally named `theme-set` silently clobbers every
    other plugin's theme-set hook. Ours must be uniquely named.
    """

    def test_hook_is_uniquely_named(self):
        hooks = sorted(p.name for p in (ROOT / "hooks").iterdir())
        self.assertIn("docker-theme-set", hooks)
        self.assertNotIn("theme-set", hooks)

    def test_install_uses_the_unique_name(self):
        text = (ROOT / "install.sh").read_text()
        self.assertIn("hooks/docker-theme-set", text)


class HookSelfLocates(unittest.TestCase):
    """HAZARD: an installed hook is copied to the hooks dir, so
    $(dirname "$BASH_SOURCE")/.. resolves to the hooks dir, not the plugin. The
    hook must self-locate instead.
    """

    def setUp(self):
        self.text = (ROOT / "hooks/docker-theme-set").read_text()

    def test_does_not_assume_sibling_plugin_dir(self):
        self.assertNotIn('dirname "$BASH_SOURCE"', self.text)

    def test_searches_known_locations(self):
        self.assertIn("OMARCHY_DOCKER_DIR", self.text)
        self.assertIn("Maximilian-Maag.docker", self.text)
        self.assertIn("omarchy-docker", self.text)


class NoBakedPalette(unittest.TestCase):
    """HAZARD: a plugin that "supports themes" with a hardcoded palette drifts
    from the applied theme. The CLI must read colours.toml at runtime and carry
    no hex literal of its own.
    """

    def test_source_contains_no_hex_colour_literal(self):
        text = CLI.read_text()
        matches = re.findall(r"#[0-9a-fA-F]{6}\b", text)
        self.assertEqual(matches, [], "hardcoded colours found: %s" % matches)

    def test_output_changes_with_the_theme(self):
        dark = dock.render_table(
            [{"Names": "web", "Image": "nginx", "State": "running", "Status": "Up"}],
            {"accent": "#111111", "running": "#222222", "stopped": "#333333", "muted": "#444444"},
            color=True)
        other = dock.render_table(
            [{"Names": "web", "Image": "nginx", "State": "running", "Status": "Up"}],
            {"accent": "#aaaaaa", "running": "#bbbbbb", "stopped": "#cccccc", "muted": "#dddddd"},
            color=True)
        self.assertNotEqual(dark, other)
        self.assertIn(dock.ansi_fg("#222222"), dark)
        self.assertIn(dock.ansi_fg("#bbbbbb"), other)


class RunnerSeam(unittest.TestCase):
    """HAZARD: if docker were called directly from many places, the tests would
    need a live daemon. Every call must go through the one injectable seam.
    """

    def test_seam_exists(self):
        src = CLI.read_text()
        self.assertIn("def default_runner", src)
        self.assertIn("def system", src)
        self.assertIn("def docker", src)

    def test_no_direct_subprocess_docker_call(self):
        # subprocess is only touched inside default_runner; there must be no
        # second `subprocess.run(["docker"` call site.
        src = CLI.read_text()
        self.assertNotIn('subprocess.run(["docker"', src)


class DockerGroupHonesty(unittest.TestCase):
    """HAZARD: pretending the daemon works when the user is not in the docker
    group. `status` must say so and print the exact fix.
    """

    def test_fix_is_printed_without_membership(self):
        text = dock.render_status({"reachable": False, "group_gid": 966, "in_group": False,
                                   "theme": ""})
        self.assertIn("usermod -aG docker", text)

    def test_no_fix_when_member(self):
        text = dock.render_status({"reachable": False, "group_gid": 966, "in_group": True,
                                   "theme": ""})
        self.assertNotIn("usermod", text)

    def test_group_membership_is_actually_checked(self):
        self.assertTrue(dock.user_in_group(966, {966, 1000}))
        self.assertFalse(dock.user_in_group(966, {1000}))


class BindingsShape(unittest.TestCase):
    """The Lua module is loaded by the compositor, not executed by any runner, so
    its shape is pinned here."""

    def setUp(self):
        self.text = (ROOT / "bin/bindings.lua").read_text()

    def test_binds_and_unbinds(self):
        self.assertIn("hl.unbind(", self.text)
        self.assertIn("o.bind(", self.text)

    def test_opens_the_container_view(self):
        self.assertIn("omarchy-docker list", self.text)

    def test_uses_the_floating_app_id(self):
        self.assertIn("org.omarchy.docker", self.text)

    def test_install_wires_it(self):
        self.assertIn("docker-bindings", (ROOT / "install.sh").read_text())


class KeybindingRenderedFromConfig(unittest.TestCase):
    """HAZARD: config/docker.json's `keybinding` had no reader — the binding was
    hardcoded in bin/bindings.lua and install.sh copied it verbatim, so editing
    the config did nothing. The installed module must carry the configured value.
    """

    def test_rendered_binding_uses_the_configured_keybinding(self):
        rendered = dock.render_bindings({"keybinding": "SUPER + SHIFT + D"})
        self.assertIn('o.bind("SUPER + SHIFT + D", "Docker containers"', rendered)
        self.assertIn('hl.unbind("SUPER + SHIFT + D")', rendered)
        self.assertNotIn(dock.KEYBINDING_PLACEHOLDER, rendered)

    def test_shipped_module_is_a_template(self):
        text = (ROOT / "bin" / "bindings.lua").read_text()
        self.assertIn(dock.KEYBINDING_PLACEHOLDER, text)

    def test_install_renders_instead_of_copying_verbatim(self):
        text = (ROOT / "install.sh").read_text()
        self.assertIn('"$BIN_SRC" bindings', text)
        self.assertNotIn('cp "$PLUGIN_DIR/bin/bindings.lua"', text)

    def test_default_keybinding_is_used_without_config(self):
        self.assertIn(dock.DEFAULT_CONFIG["keybinding"], dock.render_bindings({}))


class KeybindingCannotInjectLua(unittest.TestCase):
    """HAZARD: the configured keybinding is substituted into a double-quoted Lua
    string literal in bin/bindings.lua. A value carrying a quote, backslash or
    newline would close the literal and inject Lua the compositor then executes.
    It must be refused, not rendered.
    """

    HOSTILE = [
        'D", dofile("/etc/passwd")\n--',
        "SUPER + \\ + D",
        "SUPER + D\nmalicious()",
        "SUPER + ' + D",
    ]

    def test_hostile_keybinding_is_refused(self):
        for value in self.HOSTILE:
            with self.assertRaises(ValueError):
                dock.render_bindings({"keybinding": value})

    def test_validate_keybinding_is_the_guard(self):
        for value in self.HOSTILE:
            with self.assertRaises(ValueError):
                dock.validate_keybinding(value)

    def test_hostile_value_never_reaches_the_module(self):
        for value in self.HOSTILE:
            try:
                rendered = dock.render_bindings({"keybinding": value})
            except ValueError:
                continue
            self.fail("hostile keybinding was rendered: %r" % rendered)

    def test_clean_keybinding_still_renders(self):
        rendered = dock.render_bindings({"keybinding": "SUPER + SHIFT + D"})
        self.assertIn('o.bind("SUPER + SHIFT + D"', rendered)
        self.assertNotIn(dock.KEYBINDING_PLACEHOLDER, rendered)


class InvalidMaxRowsIsIgnored(unittest.TestCase):
    """HAZARD: `list` sliced containers[:max_rows] with the raw config value, so a
    non-integer max_rows raised an uncaught TypeError. It must be coerced or
    ignored with a clear message, never crash.
    """

    def test_bad_values_coerce_to_none(self):
        for value in ("forty", "4o", [], {}, "3.5", "", None):
            self.assertIsNone(dock.coerce_max_rows(value))

    def test_non_positive_coerces_to_none(self):
        for value in (0, -1, "0"):
            self.assertIsNone(dock.coerce_max_rows(value))

    def test_good_values_preserved(self):
        self.assertEqual(dock.coerce_max_rows(1), 1)
        self.assertEqual(dock.coerce_max_rows(5), 5)
        self.assertEqual(dock.coerce_max_rows("7"), 7)

    def test_visible_rows_never_raises_on_a_string_cap(self):
        containers = list(range(10))
        self.assertEqual(dock.visible_rows(containers, "nonsense"), containers)
        self.assertEqual(len(dock.visible_rows(containers, 3)), 3)

    def test_list_survives_a_non_integer_max_rows(self):
        import contextlib
        import io
        containers = [{"Names": "web", "Image": "nginx", "State": "running", "Status": "Up"}]
        ps = "\n".join(json.dumps(c) for c in containers)
        real = dock.default_runner
        dock.default_runner = lambda argv: (0, ps, "")
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".json") as fh:
                fh.write(json.dumps({"max_rows": "forty"}))
                fh.flush()
                err = io.StringIO()
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                    rc = dock.main(["--config", fh.name, "list"])
        finally:
            dock.default_runner = real
        self.assertEqual(rc, 0)
        self.assertIn("max_rows", err.getvalue())

    def test_list_accepts_a_valid_integer_cap(self):
        import contextlib
        import io
        containers = [{"Names": "c%d" % i, "Image": "x", "State": "running", "Status": "Up"}
                      for i in range(5)]
        ps = "\n".join(json.dumps(c) for c in containers)
        real = dock.default_runner
        dock.default_runner = lambda argv: (0, ps, "")
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".json") as fh:
                fh.write(json.dumps({"max_rows": 2}))
                fh.flush()
                err = io.StringIO()
                out = io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    rc = dock.main(["--config", fh.name, "list"])
        finally:
            dock.default_runner = real
        self.assertEqual(rc, 0)
        self.assertNotIn("max_rows", err.getvalue())
        self.assertIn("c0", out.getvalue())
        self.assertNotIn("c2", out.getvalue())


class LiveThemeNameIsAuthoritative(unittest.TestCase):
    """HAZARD: recovering the applied theme's name by colour equality alone left a
    NON-catalogued theme nameless ('(unknown)'), because the applied colours match
    no installed theme. Omarchy's live ``current/theme.name`` is authoritative and
    must win; the colour match is only a fallback.
    """

    def setUp(self):
        self._state = tempfile.TemporaryDirectory()
        self.addCleanup(self._state.cleanup)
        self._old_state = os.environ.get("XDG_STATE_HOME")
        os.environ["XDG_STATE_HOME"] = self._state.name
        self.addCleanup(self._restore_state)

    def _restore_state(self):
        if self._old_state is None:
            os.environ.pop("XDG_STATE_HOME", None)
        else:
            os.environ["XDG_STATE_HOME"] = self._old_state

    def _write_name(self, text):
        namedir = pathlib.Path(self._state.name) / "omarchy/current"
        namedir.mkdir(parents=True, exist_ok=True)
        (namedir / "theme.name").write_text(text)

    def test_name_file_matching_no_installed_theme_resolves_to_that_name(self):
        self._write_name("yellow-on-black\n")
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            (root / "nord").mkdir()
            (root / "nord/colors.toml").write_text('accent = "#88c0d0"\n')
            self.assertEqual(
                dock.resolve_theme_name({"accent": "#000000"}, [root / "nord"]),
                "yellow-on-black")

    def test_without_a_name_file_the_colour_match_is_used(self):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            (root / "nord").mkdir()
            (root / "nord/colors.toml").write_text('accent = "#88c0d0"\n')
            self.assertEqual(
                dock.resolve_theme_name({"accent": "#88c0d0"}, [root / "nord"]), "nord")

    def test_omarchy_theme_name_normalises_spaced_title_case(self):
        self._write_name("Tokyo Night\n")
        self.assertEqual(dock.omarchy_theme_name(), "tokyo-night")


class DedicatedThemePath(unittest.TestCase):
    """HAZARD: writing the theme file over something the user owns. Ours is a
    dedicated file.
    """

    def test_default_path_is_dedicated(self):
        path = dock.theme_path({})
        self.assertEqual(path.name, "omarchy-docker-theme.json")


class ManifestContract(unittest.TestCase):
    """The policy check enforces this, but pin it here too so a rename fails
    loudly in the test suite as well.
    """

    def test_id_is_owner_namespaced(self):
        manifest = json.loads((ROOT / "manifest.json").read_text())
        self.assertEqual(manifest["id"], "Maximilian-Maag.docker")
        self.assertFalse(manifest["id"].startswith("omarchy."))

    def test_version_matches_changelog(self):
        manifest = json.loads((ROOT / "manifest.json").read_text())
        text = (ROOT / "CHANGELOG.md").read_text()
        versions = re.findall(r"^##\s*\[?v?([0-9]+\.[0-9]+\.[0-9]+)", text, re.M)
        self.assertEqual(manifest["version"], versions[0])


if __name__ == "__main__":
    unittest.main()
