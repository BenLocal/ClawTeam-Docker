"""Validate startup configuration before touching a persisted Magpie profile."""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "bootstrap", Path(__file__).resolve().parents[1] / "magpie_bootstrap.py"
)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class BootstrapTests(unittest.TestCase):
    def config(self):
        return {
            "providers": [
                {
                    "id": "relay",
                    "url_env": "TEST_BASE",
                    "key_env": "TEST_KEY",
                    "models": ["test-model"],
                }
            ],
            "groups": [
                {"id": "coding", "models": ["relay/test-model"], "stays": "off"}
            ],
            "claude": {"model": "group/coding"},
        }

    def test_updates_existing_provider_and_preserves_claude_state(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            magpie_dir = home / ".config/magpie"
            magpie_dir.mkdir(parents=True)
            (magpie_dir / "providers.json").write_text(
                json.dumps({"providers": [{"id": "relay"}]})
            )
            (home / ".claude.json").write_text('{"unrelated": "keep"}')
            config = home / "providers.yaml"
            config.write_text(json.dumps(self.config()))
            with (
                patch.dict(
                    os.environ,
                    {
                        "HOME": directory,
                        "XDG_CONFIG_HOME": str(home / ".config"),
                        "TEST_BASE": "http://gateway:8000/v1",
                        "TEST_KEY": "secret",
                        "CLAWTEAM_MODEL": "relay/test-model",
                    },
                ),
                patch.object(bootstrap, "magpie") as cli,
                patch.object(bootstrap, "PENDING_PATH", home / "pending"),
                patch.object(bootstrap.shutil, "which", return_value=None),
            ):
                bootstrap.configure(config)
            calls = cli.call_args_list
            self.assertEqual(calls[0].args[:3], ("provider", "set", "relay"))
            self.assertIn("key=secret", calls[0].args)
            self.assertIn("url=http://gateway:8000/v1", calls[0].args)
            self.assertEqual(calls[-1].args, ("claude", "relay/test-model"))
            state = json.loads((home / ".claude.json").read_text())
            self.assertEqual(state["unrelated"], "keep")
            self.assertTrue(state["hasCompletedOnboarding"])
            self.assertTrue(state["projects"][os.getcwd()]["hasTrustDialogAccepted"])

    def test_installed_dsh_follows_the_claude_model(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home / "providers.yaml"
            config.write_text(json.dumps(self.config()))
            for installed, expected in (("/usr/local/bin/dsh", True), (None, False)):
                with (
                    patch.dict(
                        os.environ,
                        {
                            "HOME": directory,
                            "XDG_CONFIG_HOME": str(home / ".config"),
                            "TEST_BASE": "http://gateway:8000/v1",
                            "TEST_KEY": "secret",
                            "CLAWTEAM_MODEL": "relay/test-model",
                        },
                    ),
                    patch.object(bootstrap, "magpie") as cli,
                    patch.object(bootstrap, "PENDING_PATH", home / "pending"),
                    patch.object(bootstrap.shutil, "which", return_value=installed),
                ):
                    bootstrap.configure(config)
                calls = [call.args for call in cli.call_args_list]
                self.assertIn(("claude", "relay/test-model"), calls)
                self.assertEqual(("dsh", "relay/test-model") in calls, expected)

    def test_required_empty_key_waits_and_filled_key_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            path = home / "providers.yaml"
            config = self.config()
            config["providers"][0]["key_required"] = True
            path.write_text(json.dumps(config))
            pending = home / "pending"
            with (
                patch.dict(
                    os.environ,
                    {
                        "HOME": directory,
                        "XDG_CONFIG_HOME": str(home / ".config"),
                        "TEST_BASE": "http://gateway/v1",
                        "TEST_KEY": "",
                        "CLAWTEAM_MODEL": "",
                    },
                ),
                patch.object(bootstrap, "magpie") as cli,
                patch.object(bootstrap, "PENDING_PATH", pending),
            ):
                bootstrap.configure(path)
                self.assertEqual(pending.read_text(), "relay")
                self.assertIn("key=clawteam-unconfigured", cli.call_args_list[0].args)
                os.environ["TEST_KEY"] = "filled-key"
                cli.reset_mock()
                bootstrap.configure(path)
                self.assertFalse(pending.exists())
                self.assertIn("key=filled-key", cli.call_args_list[0].args)

    def test_validates_all_entries_before_any_mutation(self):
        config = self.config()
        config["groups"][0]["stays"] = False
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(
                os.environ, {"TEST_BASE": "http://gateway/v1", "TEST_KEY": "secret"}
            ),
            patch.object(bootstrap, "magpie") as cli,
        ):
            path = Path(directory) / "providers.yaml"
            path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                bootstrap.configure(path)
            cli.assert_not_called()

    def test_missing_key_environment_is_rejected(self):
        with (
            patch.dict(os.environ, {"TEST_BASE": "http://gateway/v1"}, clear=True),
            self.assertRaisesRegex(ValueError, "key_env"),
        ):
            bootstrap.validate(self.config())

    def test_duplicate_provider_ids_are_rejected(self):
        config = self.config()
        config["providers"].append(dict(config["providers"][0]))
        with self.assertRaisesRegex(ValueError, "唯一"):
            bootstrap.validate(config)


if __name__ == "__main__":
    unittest.main()
