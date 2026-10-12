"""Regression tests — one per real bug / design hazard this plugin must not regress.

Each test fails if the guard is removed, and names the hazard it pins.
"""

import importlib.machinery
import importlib.util
import json
import pathlib
import re
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
