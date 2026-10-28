"""Write Git credentials only from complete, valid settings and keep them private."""

import importlib.util
import stat
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "git_credentials_bootstrap", ROOT / "git_credentials_bootstrap.py"
)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class GitCredentialTests(unittest.TestCase):
    def environ(self, directory, **values):
        return {"XDG_CONFIG_HOME": directory, **values}

    def test_unconfigured_does_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            bootstrap.configure(self.environ(directory))
            self.assertFalse(Path(directory, "clawteam-docker").exists())

    def test_writes_encoded_private_store_line(self):
        with tempfile.TemporaryDirectory() as directory:
            bootstrap.configure(
                self.environ(
                    directory,
                    GIT_CREDENTIAL_URL="https://git.example.com:8443/",
                    GIT_CREDENTIAL_USERNAME="dev@corp",
                    GIT_CREDENTIAL_PASSWORD="p@ss:w/rd #1",
                )
            )
            path = Path(directory, "clawteam-docker/git-credentials")
            self.assertEqual(
                path.read_text(),
                "https://dev%40corp:p%40ss%3Aw%2Frd%20%231@git.example.com:8443\n",
            )
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_partial_or_invalid_settings_write_nothing(self):
        cases = [
            {"GIT_CREDENTIAL_URL": "https://git.example.com"},
            {
                "GIT_CREDENTIAL_URL": "https://git.example.com/group/repo.git",
                "GIT_CREDENTIAL_USERNAME": "u",
                "GIT_CREDENTIAL_PASSWORD": "p",
            },
            {
                "GIT_CREDENTIAL_URL": "ssh://git.example.com",
                "GIT_CREDENTIAL_USERNAME": "u",
                "GIT_CREDENTIAL_PASSWORD": "p",
            },
            {
                "GIT_CREDENTIAL_URL": "https://u:p@git.example.com",
                "GIT_CREDENTIAL_USERNAME": "u",
                "GIT_CREDENTIAL_PASSWORD": "p",
            },
        ]
        for values in cases:
            with (
                self.subTest(values=values),
                tempfile.TemporaryDirectory() as directory,
            ):
                with self.assertRaises(ValueError):
                    bootstrap.configure(self.environ(directory, **values))
                self.assertFalse(Path(directory, "clawteam-docker").exists())


if __name__ == "__main__":
    unittest.main()
