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


class SealClient:
    def __init__(self, initialized, sealed):
        self.status = {"initialized": initialized, "sealed": sealed, "t": 1}
        self.calls = []

    def call(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if path == "sys/seal-status":
            return self.status
        if path == "sys/init":
            self.status.update(initialized=True, sealed=True)
            return {"keys_base64": ["k1"], "root_token": "root-1", "keys": ["hex"]}
        if path == "sys/unseal":
            self.status["sealed"] = False
        return {}


class AutoUnsealTests(unittest.TestCase):
    def test_initializes_once_then_unseals_with_stored_key(self):
        with tempfile.TemporaryDirectory() as directory:
            init_file = Path(directory, "init.json")
            client = SealClient(initialized=False, sealed=True)
            self.assertEqual(
                bootstrap.auto_unseal_state(client, init_file), "刚完成初始化"
            )
            self.assertEqual(stat.S_IMODE(init_file.stat().st_mode), 0o600)
            stored = json.loads(init_file.read_text())
            self.assertEqual(stored, {"keys_base64": ["k1"], "root_token": "root-1"})
            self.assertEqual(bootstrap.auto_unseal_state(client, init_file), "正在解封")
            self.assertIn(("PUT", "sys/unseal", {"key": "k1"}), client.calls)
            self.assertEqual(bootstrap.auto_unseal_state(client, init_file), "ready")
            self.assertEqual(
                [c for c in client.calls if c[1] == "sys/init"],
                [("PUT", "sys/init", {"secret_shares": 1, "secret_threshold": 1})],
            )

    def test_sealed_without_stored_keys_waits_for_a_person(self):
        with tempfile.TemporaryDirectory() as directory:
            client = SealClient(initialized=True, sealed=True)
            state = bootstrap.auto_unseal_state(client, Path(directory, "init.json"))
            self.assertIn("需要人工解封", state)
            self.assertNotIn("sys/unseal", [path for _, path, _ in client.calls])

    def test_reinitialization_keeps_previous_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            init_file = Path(directory, "init.json")
            init_file.write_text('{"keys_base64": ["old"], "root_token": "old"}')
            bootstrap.auto_unseal_state(
                SealClient(initialized=False, sealed=True), init_file
            )
            backups = list(Path(directory).glob("init.json.bak-*"))
            self.assertEqual(len(backups), 1)
            self.assertIn("old", backups[0].read_text())

    def test_unreachable_server_is_waited_for(self):
        class Down:
            def call(self, *args):
                raise OSError("refused")

        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                bootstrap.auto_unseal_state(Down(), Path(directory, "init.json")),
                "未启动",
            )


if __name__ == "__main__":
    unittest.main()
