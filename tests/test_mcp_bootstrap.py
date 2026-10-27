"""Reject invalid MCP definitions before changing any Library entries."""

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
    "mcp_bootstrap", ROOT / "mcp_bootstrap.py"
)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class MCPTests(unittest.TestCase):
    def test_installs_once_rechecks_and_reinstalls_changed_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "installed"
            counter = root / "count"
            server = {
                "name": "fixture",
                "install": {
                    "command": [
                        sys.executable,
                        "-c",
                        f"from pathlib import Path; Path({str(marker)!r}).touch(); p=Path({str(counter)!r}); p.write_text(p.read_text()+'x' if p.exists() else 'x')",
                    ],
                    "check": [
                        sys.executable,
                        "-c",
                        f"from pathlib import Path; raise SystemExit(0 if Path({str(marker)!r}).exists() else 1)",
                    ],
                },
            }
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(root / "config")}):
                bootstrap.install_server(server)
                bootstrap.install_server(server)
                self.assertEqual(counter.read_text(), "x")
                server["install"]["command"][2] += "; print('new version')"
                bootstrap.install_server(server)
                self.assertEqual(counter.read_text(), "xx")

    def test_failed_install_is_not_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            server = {
                "name": "fails",
                "install": {
                    "command": [sys.executable, "-c", "raise SystemExit(2)"],
                    "check": [sys.executable, "-c", "raise SystemExit(1)"],
                },
            }
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
                with self.assertRaisesRegex(RuntimeError, "依赖安装失败"):
                    bootstrap.install_server(server)
                self.assertFalse(list(Path(directory).rglob("*.json")))

    def test_all_servers_validated_before_network(self):
        good = {
            "name": "good",
            "transport": "stdio",
            "command": "python3",
            "agents": ["claude"],
        }
        for invalid in (
            {},
            dict(good, args="wrong"),
            dict(good, env={"KEY": False}),
            dict(good, url="http://example.com"),
            {
                "name": "bad",
                "transport": "http",
                "url": "file:///tmp/mcp",
                "agents": ["claude"],
            },
        ):
            with (
                self.subTest(invalid=invalid),
                tempfile.TemporaryDirectory() as directory,
            ):
                path = Path(directory, "mcp.yaml")
                path.write_text(json.dumps({"servers": [good, invalid]}))
                with patch.object(bootstrap, "Library") as client:
                    with self.assertRaises((ValueError, TypeError)):
                        bootstrap.configure(path)
                    client.assert_not_called()

    def test_upserts_named_server_without_removing_unlisted_ones(self):
        server = {
            "name": "configured",
            "transport": "stdio",
            "command": "python3",
            "agents": ["claude"],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "mcp.yaml")
            path.write_text(json.dumps({"servers": [server]}))
            with (
                patch.object(bootstrap, "Library") as client,
                patch.dict(os.environ, {"MAGPIE_WEB_KEY": "test"}),
            ):
                client.return_value.request.return_value = {
                    "agents": [{"id": "claude"}],
                    "servers": [{"name": "configured"}, {"name": "manual"}],
                }
                bootstrap.configure(path)
                client.return_value.change.assert_called_once_with(
                    "servers/save", {"old": "configured", "server": server}
                )

    def test_empty_config_does_not_contact_magpie(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "mcp.yaml")
            path.write_text("servers: []\n")
            with patch.object(bootstrap, "Library") as client:
                bootstrap.configure(path)
                client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
