"""A failed plugin install is skipped and retried later instead of stopping startup."""

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location(
    "plugin_bootstrap", ROOT / "plugin_bootstrap.py"
)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)

FAKE_MAGPIE = """#!/bin/sh
# plugin add <source>
if [ "$3" = "bad" ]; then
    echo "fetch https://user:SECRET@example.invalid/repo failed" >&2
    exit 1
fi
echo "✓ added $3@1.0.0"
"""


class PluginTests(unittest.TestCase):
    def run_configure(self, plugins):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        magpie = bin_dir / "magpie"
        magpie.write_text(FAKE_MAGPIE)
        magpie.chmod(0o755)
        config = root / "plugin.yaml"
        config.write_text(json.dumps({"plugins": plugins}))
        environment = {
            "XDG_CONFIG_HOME": str(root / "config"),
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        }
        stderr = io.StringIO()
        with patch.dict(os.environ, environment), contextlib.redirect_stderr(stderr):
            failed = bootstrap.configure(config)
        state_file = root / "config/clawteam-docker/plugin-sources.json"
        state = json.loads(state_file.read_text()) if state_file.exists() else {}
        return failed, state, stderr.getvalue()

    def test_failed_install_is_skipped_and_not_recorded(self):
        failed, state, stderr = self.run_configure(["bad", "good"])
        self.assertEqual(failed, [1])
        self.assertEqual(state, {"good": "good@1.0.0"})
        self.assertIn("第 1 个插件安装失败", stderr)
        self.assertNotIn("SECRET", stderr)

    def test_timeout_is_treated_as_failed_install(self):
        with patch.object(
            bootstrap.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["magpie"], 360),
        ):
            failed, state, _ = self.run_configure(["slow"])
        self.assertEqual(failed, [1])
        self.assertEqual(state, {})

    def test_invalid_config_still_fails_before_installing(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory, "plugin.yaml")
            config.write_text("plugins: [valid, 123]\n")
            with (
                patch.object(bootstrap.subprocess, "run") as run,
                self.assertRaises(TypeError),
            ):
                bootstrap.configure(config)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
