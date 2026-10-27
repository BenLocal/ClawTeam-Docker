"""Exercise config validation, authentication and failed writes without retries."""

import importlib.util
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "skills_bootstrap", Path(__file__).resolve().parents[1] / "skills_bootstrap.py"
)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class SkillsTests(unittest.TestCase):
    def test_repository_aliases_and_refs(self):
        self.assertEqual(
            bootstrap.repository("https://code.example/group/repo.git"),
            bootstrap.repository("git@code.example:group/repo.git"),
        )
        self.assertEqual(
            bootstrap.repository("https://github.com/owner/repo/tree/main/skills"),
            bootstrap.repository("owner/repo"),
        )

    def test_update_leaves_same_named_skill_from_another_source_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory, "skills.yaml")
            config.write_text(
                "sources: [{source: 'https://git.example/team/wanted.git', agents: [claude]}]\n"
            )
            with (
                patch.dict(os.environ, {"MAGPIE_WEB_KEY": "test"}),
                patch.object(bootstrap, "Library") as client,
            ):
                client.return_value.request.side_effect = [
                    {"agents": [{"id": "claude"}]},
                    {
                        "kind": "git",
                        "candidates": [
                            {"name": "shared", "path": "skills/shared", "have": True}
                        ],
                    },
                    {
                        "skills": [
                            {
                                "name": "shared",
                                "kind": "git",
                                "repo": "git.example/another/repo",
                            }
                        ]
                    },
                ]
                bootstrap.configure(config, update=True)
                client.return_value.change.assert_called_once_with("all/sync", {})

    def test_update_reports_local_edits_as_failure(self):
        with patch.object(
            bootstrap.Library,
            "request",
            return_value={"result": {"unupdated": [{"what": "skill:changed"}]}},
        ):
            client = object.__new__(bootstrap.Library)
            with self.assertRaisesRegex(RuntimeError, "本地修改"):
                client.change("skills/update-some", {"names": ["changed"]})

    def test_validates_all_sources_before_using_library(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory, "skills.yaml")
            for value in (
                None,
                {"sources": "wrong"},
                {"sources": [{"source": "", "agents": ["claude"]}]},
                {"sources": [{"source": "/skills", "agents": []}]},
                {"sources": [{"source": "/skills", "agents": "claude"}]},
                {"sources": [{"source": "/skills", "agents": [1]}]},
                {
                    "sources": [
                        {"source": "/skills", "agents": ["claude"], "typo": True}
                    ]
                },
            ):
                with (
                    self.subTest(value=value),
                    patch.object(bootstrap, "Library") as client,
                ):
                    config.write_text(json.dumps(value))
                    with self.assertRaises((ValueError, TypeError)):
                        bootstrap.configure(config)
                    client.assert_not_called()

    def test_empty_sources_need_no_key_or_network(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory, "skills.yaml")
            config.write_text("sources: []\n")
            with patch.object(bootstrap, "Library") as client:
                bootstrap.configure(config)
                client.assert_not_called()

    def test_unknown_agent_rejected_before_probe_or_install(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory, "skills.yaml")
            config.write_text("sources: [{source: /skills, agents: [cluade]}]\n")
            with (
                patch.dict(os.environ, {"MAGPIE_WEB_KEY": "test"}),
                patch.object(bootstrap, "Library") as client,
            ):
                client.return_value.request.return_value = {
                    "agents": [{"id": "claude"}]
                }
                with self.assertRaisesRegex(ValueError, "未识别"):
                    bootstrap.configure(config)
                client.return_value.request.assert_called_once_with("/api/library")
                client.return_value.change.assert_not_called()

    def test_cookie_auth_proxy_bypass_and_failed_install_not_retried(self):
        calls = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path == "/api/library":
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"agents": [{"id": "claude"}]}')
                    return
                if self.path == "/":
                    self.send_response(200)
                else:
                    self.send_response(302)
                    self.send_header("Set-Cookie", "session=test; Path=/")
                    self.send_header("Location", "/")
                self.end_headers()

            def do_POST(self):
                calls.append(self.path)
                if self.headers.get("Cookie") != "session=test":
                    self.send_response(401)
                    self.end_headers()
                    return
                if self.path.endswith("probe"):
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(
                        json.dumps(
                            {"candidates": [{"path": "one", "have": False}]}
                        ).encode()
                    )
                else:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b"private-repository-credential")

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                config = Path(directory, "skills.yaml")
                config.write_text("sources: [{source: /skills, agents: [claude]}]")
                with (
                    patch.object(
                        bootstrap, "BASE", f"http://127.0.0.1:{server.server_port}"
                    ),
                    patch.dict(
                        os.environ,
                        {
                            "MAGPIE_WEB_KEY": "key with / symbols",
                            "HTTP_PROXY": "http://127.0.0.1:1",
                            "NO_PROXY": "",
                        },
                    ),
                    self.assertRaisesRegex(RuntimeError, "HTTP 500") as error,
                ):
                    bootstrap.configure(config)
                self.assertNotIn("credential", str(error.exception))
                self.assertEqual(
                    calls, ["/api/library/skills/probe", "/api/library/skills/install"]
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
