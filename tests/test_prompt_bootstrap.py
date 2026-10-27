"""Validate partial Instructions imports before changing the persisted profile."""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location(
    "prompt_bootstrap", ROOT / "prompt_bootstrap.py"
)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class PromptTests(unittest.TestCase):
    def test_empty_config_preserves_existing_profile_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "prompt.yaml")
            path.write_text("instructions: {}\n")
            with patch.object(bootstrap, "Library") as client:
                bootstrap.configure(path)
                client.assert_not_called()

    def test_invalid_fields_rejected_before_network(self):
        for value in (
            None,
            [],
            {"typo": "x"},
            {"shared": True},
            {"agents": "claude"},
            {"extra": {"claude": False}},
        ):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                path = Path(directory, "prompt.yaml")
                path.write_text(json.dumps({"instructions": value}))
                with patch.object(bootstrap, "Library") as client:
                    with self.assertRaises((ValueError, TypeError)):
                        bootstrap.configure(path)
                    client.assert_not_called()

    def test_partial_config_and_explicit_empty_values_pass_through(self):
        for values in ({"shared": ""}, {"agents": []}, {"extra": {"claude": ""}}):
            with (
                self.subTest(values=values),
                tempfile.TemporaryDirectory() as directory,
            ):
                path = Path(directory, "prompt.yaml")
                path.write_text(json.dumps({"instructions": values}))
                with (
                    patch.object(bootstrap, "Library") as client,
                    patch.dict(os.environ, {"MAGPIE_WEB_KEY": "test"}),
                ):
                    client.return_value.request.side_effect = [
                        {"instructions": {"agents": [{"agent": "claude"}]}},
                        {"result": {"problems": []}},
                    ]
                    bootstrap.configure(path)
                    self.assertEqual(
                        client.return_value.request.call_args.args,
                        ("/api/library/instructions/save", values),
                    )

    def test_unknown_agent_is_not_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "prompt.yaml")
            path.write_text("instructions: {extra: {cluade: hello}}\n")
            with (
                patch.object(bootstrap, "Library") as client,
                patch.dict(os.environ, {"MAGPIE_WEB_KEY": "test"}),
            ):
                client.return_value.request.return_value = {
                    "instructions": {"agents": [{"agent": "claude"}]}
                }
                with self.assertRaises(ValueError):
                    bootstrap.configure(path)
                client.return_value.request.assert_called_once_with("/api/library")


if __name__ == "__main__":
    unittest.main()
