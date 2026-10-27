"""Keep Docker auth intact while applying or clearing runtime proxies."""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "proxy_bootstrap", Path(__file__).resolve().parents[1] / "proxy_bootstrap.py"
)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class ProxyBootstrapTests(unittest.TestCase):
    def test_docker_normalization_does_not_change_application_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {
                    "DOCKER_CONFIG": directory,
                    "MIRROR_HTTP_PROXY": "http://mirror:3128",
                    "HTTP_PROXY": "http://application:8080",
                    "NO_PROXY": "registry.internal",
                },
                clear=True,
            ):
                original = dict(os.environ)
                bootstrap.configure()
                self.assertEqual(dict(os.environ), original)
                child = bootstrap.download_environment()
                self.assertEqual(child["HTTPS_PROXY"], "http://mirror:3128")
                self.assertEqual(dict(os.environ), original)
            proxies = json.loads(Path(directory, "config.json").read_text())["proxies"][
                "default"
            ]
            self.assertEqual(proxies["httpProxy"], "http://mirror:3128")
            self.assertIn("registry.internal", proxies["noProxy"])
            self.assertIn("127.0.0.1", proxies["noProxy"])

    def test_proxy_configuration_preserves_registry_auth_and_other_daemons(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            auth = {"registry.example": {"auth": "existing-login"}}
            path.write_text(
                json.dumps(
                    {
                        "auths": auth,
                        "proxies": {"tcp://other:2376": {"noProxy": "other"}},
                    }
                )
            )
            with patch.dict(
                os.environ,
                {
                    "DOCKER_CONFIG": directory,
                    "HTTP_PROXY": "http://proxy:3128",
                    "HTTPS_PROXY": "http://proxy:3128",
                    "NO_PROXY": "localhost,127.0.0.1",
                },
                clear=True,
            ):
                bootstrap.configure()
            config = json.loads(path.read_text())
            self.assertEqual(config["auths"], auth)
            self.assertEqual(
                config["proxies"]["tcp://other:2376"], {"noProxy": "other"}
            )
            self.assertEqual(
                config["proxies"]["default"]["httpProxy"], "http://proxy:3128"
            )
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_clearing_runtime_proxy_removes_previous_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"proxies":{"default":{"httpProxy":"http://old:3128"}}}')
            with patch.dict(os.environ, {"DOCKER_CONFIG": directory}, clear=True):
                bootstrap.configure()
            self.assertEqual(
                json.loads(path.read_text())["proxies"]["default"],
                {"noProxy": "localhost,127.0.0.1,::1"},
            )

    def test_invalid_existing_config_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text("invalid json")
            with (
                patch.dict(os.environ, {"DOCKER_CONFIG": directory}, clear=True),
                self.assertRaises(ValueError),
            ):
                bootstrap.configure()
            self.assertEqual(path.read_text(), "invalid json")


if __name__ == "__main__":
    unittest.main()
