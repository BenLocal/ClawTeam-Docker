"""Validate openbao.yaml fully and import it idempotently before rendering files."""

import importlib.util
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location(
    "openbao_bootstrap", ROOT / "openbao_bootstrap.py"
)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class FakeClient:
    def __init__(self, mounts=None, auth=None, stored=None):
        self.calls = []
        self.token = ""
        self.mounts = mounts or {}
        self.auth = auth or {}
        self.stored = stored or {}

    def call(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if (method, path) == ("GET", "sys/mounts"):
            return {"data": self.mounts}
        if (method, path) == ("GET", "sys/auth"):
            return {"data": self.auth}
        if method == "GET" and path.startswith("secret/data/"):
            data = self.stored.get(path.removeprefix("secret/data/"))
            return None if data is None else {"data": {"data": data}}
        if path.endswith("/role-id"):
            return {"data": {"role_id": "role-123"}}
        if path.endswith("/secret-id"):
            return {"data": {"secret_id": "secret-456"}}
        return {}

    def writes(self):
        return [call for call in self.calls if call[0] != "GET"]


def write_config(directory, config):
    path = Path(directory, "openbao.yaml")
    path.write_text(json.dumps(config))
    return path


class ConfigTests(unittest.TestCase):
    def test_accepts_secrets_and_files(self):
        with tempfile.TemporaryDirectory() as directory:
            secrets, files = bootstrap.read_config(
                write_config(
                    directory,
                    {
                        "secrets": {"team/env": {"TOKEN": "v"}},
                        "files": [{"path": "/home/node/x.env", "template": "t"}],
                    },
                )
            )
        self.assertEqual(secrets, {"team/env": {"TOKEN": "v"}})
        self.assertEqual(files, [{"path": "/home/node/x.env", "template": "t"}])

    def test_rejects_invalid_entries(self):
        cases = [
            {"other": {}},
            {"secrets": {"../escape": {"k": "v"}}},
            {"secrets": {"team/./x": {"k": "v"}}},
            {"secrets": {"team/env": {}}},
            {"secrets": {"team/env": {"k": 1}}},
            {"files": [{"path": "relative.env", "template": "t"}]},
            {"files": [{"path": "/a", "template": " "}]},
            {"files": [{"path": "/a", "template": "t", "mode": "0644"}]},
            {
                "files": [
                    {"path": "/a", "template": "t"},
                    {"path": "/a", "template": "u"},
                ]
            },
        ]
        for config in cases:
            with (
                self.subTest(config=config),
                tempfile.TemporaryDirectory() as directory,
                self.assertRaises((ValueError, TypeError)),
            ):
                bootstrap.read_config(write_config(directory, config))


class ImportTests(unittest.TestCase):
    def test_creates_mount_writes_changed_secrets_and_read_only_policy(self):
        client = FakeClient(stored={"team/same": {"k": "v"}})
        bootstrap.import_secrets(
            client, {"team/same": {"k": "v"}, "team/new": {"TOKEN": "x"}}
        )
        writes = client.writes()
        self.assertIn(
            ("POST", "sys/mounts/secret", {"type": "kv", "options": {"version": "2"}}),
            writes,
        )
        self.assertIn(
            ("POST", "secret/data/team/new", {"data": {"TOKEN": "x"}}), writes
        )
        self.assertNotIn("secret/data/team/same", [path for _, path, _ in writes])
        policy = next(
            p for m, path, p in writes if path == "sys/policies/acl/clawteam-agent"
        )
        self.assertIn(
            'path "secret/data/team/new" { capabilities = ["read"] }', policy["policy"]
        )
        self.assertNotIn("update", policy["policy"])
        self.assertIn(("POST", "sys/auth/approle", {"type": "approle"}), writes)

    def test_existing_mount_and_approle_are_reused(self):
        client = FakeClient(mounts={"secret/": {}}, auth={"approle/": {}})
        bootstrap.import_secrets(client, {"team/env": {"k": "v"}})
        paths = [path for _, path, _ in client.writes()]
        self.assertNotIn("sys/mounts/secret", paths)
        self.assertNotIn("sys/auth/approle", paths)


class ConfigureTests(unittest.TestCase):
    def test_waits_imports_and_writes_private_agent_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = write_config(
                root,
                {
                    "secrets": {"team/env": {"TOKEN": "x"}},
                    "files": [{"path": str(root / "out.env"), "template": "{{ . }}"}],
                },
            )
            token = root / "token"
            token.write_text("admin-token\n")
            client = FakeClient()
            with (
                patch.object(bootstrap, "Client", return_value=client),
                patch.object(bootstrap, "health", return_value="ready"),
            ):
                path = bootstrap.configure(config, token, home=root)
                self.assertEqual(client.token, "admin-token")
                state = root / ".openbao/agent"
                self.assertEqual((state / "role_id").read_text(), "role-123")
                self.assertEqual((state / "secret_id").read_text(), "secret-456")
                for name in ("role_id", "secret_id", "agent.json"):
                    self.assertEqual(stat.S_IMODE((state / name).stat().st_mode), 0o600)
                agent = json.loads(path.read_text())
                self.assertEqual(
                    agent["template"][0]["destination"], str(root / "out.env")
                )
                self.assertEqual(agent["template"][0]["perms"], "0600")
                method = agent["auto_auth"]["method"][0]
                self.assertEqual(method["type"], "approle")
                # A second start keeps the existing secret ID instead of minting more.
                client.calls.clear()
                bootstrap.configure(config, token, home=root)
                self.assertNotIn(
                    "auth/approle/role/clawteam-agent/secret-id",
                    [p for _, p, _ in client.calls],
                )

    def test_empty_config_does_not_contact_openbao(self):
        with tempfile.TemporaryDirectory() as directory:
            config = write_config(directory, {"secrets": {}, "files": []})
            with patch.object(bootstrap, "Client") as client:
                self.assertIsNone(bootstrap.configure(config, Path(directory, "t")))
            client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
