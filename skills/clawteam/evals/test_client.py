"""Exercise the CLI against a local HTTP server; never contact a deployed team."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "clawteam.py"
SNAPSHOT = {
    "team": {"name": "demo"},
    "taskSummary": {"pending": 1, "completed": 1, "total": 2},
    "members": [{"name": "developer", "inboxCount": 1}],
    "cost": {},
    "conflicts": {},
    "messages": [
        {
            "from": "developer",
            "to": "leader",
            "timestamp": "2026-10-28T12:00:00Z",
            "content": "完成",
        },
        {
            "from": "leader",
            "to": "developer",
            "timestamp": "2026-10-28T12:01:00Z",
            "content": "检查",
        },
    ],
    "tasks": {
        "pending": [
            {
                "id": "task-1",
                "status": "pending",
                "subject": "中文任务",
                "owner": "developer",
            }
        ],
        "completed": [{"id": "task-2", "status": "completed", "description": "完成"}],
    },
}

SNAPSHOT["messages"].reverse()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, body, status=200, content_type="application/json"):
        body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def authorized(self):
        header = self.headers.get("Authorization")
        self.server.auth.append((self.path, header))
        if "/openapi/" in self.path and header != "Bearer test-secret":
            self.respond(
                json.dumps({"error": "Invalid key: " + str(header)}), status=401
            )
            return False
        return True

    def do_GET(self):
        self.server.calls.append(("GET", self.path, None))
        if not self.authorized():
            return
        if self.path.startswith("/redirect/"):
            self.send_response(302)
            self.send_header("Location", "/leaked-key")
            self.end_headers()
            return
        if self.path.startswith("/old/"):
            self.respond('{"error":"Not found"}', status=404)
        elif self.path.endswith("/capabilities"):
            self.respond(
                json.dumps(
                    {
                        "features": [
                            "task_create_options",
                            "task_update",
                            "message_send",
                            "message_broadcast",
                            "agent_spawn",
                            "agent_list",
                        ]
                    }
                )
            )
        elif self.path.startswith("/missing/"):
            self.respond('{"error":"team missing"}', status=404)
        elif self.path.startswith("/html/"):
            self.respond("<html>login page</html>", content_type="text/html")
        elif self.path.endswith("/events/demo"):
            self.respond(
                ': heartbeat\n\ndata: {"tasks":\ndata: {"pending": []}}\n\n',
                content_type="text/event-stream",
            )
        elif self.path.endswith("/overview"):
            self.respond("[]")
        else:
            self.respond(json.dumps(SNAPSHOT, ensure_ascii=False))

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.server.calls.append(("POST", self.path, json.loads(body)))
        if not self.authorized():
            return
        if self.path.startswith("/broken/"):
            self.respond("{", status=200)
        else:
            self.respond('{"status":"ok","task_id":"new-task"}')

    def do_PATCH(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.server.calls.append(("PATCH", self.path, json.loads(body)))
        if not self.authorized():
            return
        self.respond('{"status":"ok","task":{"id":"task-1"}}')


class RemoteClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.host = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.server.calls = []
        self.server.auth = []

    def run_cli(self, *args, prefix="/clawteam/openapi/", **env):
        environment = dict(
            os.environ,
            CLAWTEAM_API_URL=self.host + prefix,
            CLAWTEAM_TEAM="demo",
            CLAWTEAM_BOARD_API_KEY="test-secret",
            CLAWTEAM_API_KEY_FILE="",
        )
        environment.update(env)
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            env=environment,
            text=True,
            capture_output=True,
            timeout=8,
            check=False,
        )

    def test_overview_bypasses_environment_proxy_and_preserves_subpath(self):
        result = self.run_cli(
            "overview",
            HTTP_PROXY="http://127.0.0.1:1",
            http_proxy="http://127.0.0.1:1",
            NO_PROXY="",
            no_proxy="",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])
        self.assertEqual(self.server.calls[0][1], "/clawteam/openapi/overview")

    def test_arguments_override_environment(self):
        result = self.run_cli(
            "--api-url", self.host + "/api", "--team", "another", "team"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        # A legacy /api root is rewritten to the authenticated /openapi root.
        self.assertEqual(self.server.calls[0][1], "/openapi/team/another")

    def test_create_preserves_unicode_file_description_and_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            description = Path(directory) / "task description.txt"
            description.write_text("第一行\n第二行 `literal` $HOME", encoding="utf-8")
            result = self.run_cli(
                "task",
                "create",
                "中文标题",
                "--description-file",
                str(description),
                "--owner",
                "leader",
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["task_id"], "new-task")
        method, path, payload = self.server.calls[-1]
        self.assertEqual((method, path), ("POST", "/clawteam/openapi/team/demo/task"))
        self.assertEqual(
            payload,
            {
                "subject": "中文标题",
                "description": "第一行\n第二行 `literal` $HOME",
                "owner": "leader",
            },
        )

    def test_server_errors_are_reported_without_traceback(self):
        result = self.run_cli("team", prefix="/missing/api")
        self.assertEqual(result.returncode, 1)
        self.assertIn("HTTP 404", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_html_is_not_reported_as_success(self):
        result = self.run_cli("team", prefix="/html/api")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")

    def test_ambiguous_create_is_never_retried(self):
        result = self.run_cli("task", "create", "test", prefix="/broken/api")
        self.assertEqual(result.returncode, 1)
        self.assertIn("未自动重试", result.stderr)
        self.assertEqual(sum(call[0] == "POST" for call in self.server.calls), 1)

    def test_sse_multiline_data_and_comment(self):
        result = self.run_cli("events", "--count", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"tasks": {"pending": []}})

    def test_invalid_input_does_not_send_requests(self):
        cases = [
            ("--connection", "115", "overview"),
            ("--ah", "ah", "overview"),
            ("task", "create", "  "),
            ("--timeout", "nan", "overview"),
            ("events", "--count", "-1"),
            ("task", "update", "task-1"),
            ("--output", "unused.json", "events"),
        ]
        for args in cases:
            with self.subTest(args=args):
                self.assertEqual(self.run_cli(*args).returncode, 2)
        self.assertEqual(self.server.calls, [])

    def test_removed_client_side_commands_are_rejected(self):
        for command in ("summary", "members", "cost", "conflicts", "messages", "watch"):
            with self.subTest(command=command):
                self.assertEqual(self.run_cli(command).returncode, 2)
        for action in ("list", "get", "wait"):
            with self.subTest(action=action):
                self.assertEqual(self.run_cli("task", action).returncode, 2)
        self.assertEqual(self.server.calls, [])

    def test_export_writes_json_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "team.json"
            result = self.run_cli("--output", str(output), "team")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(json.loads(output.read_text())["team"], {"name": "demo"})

    def test_update_uses_patch_and_preserves_empty_owner(self):
        result = self.run_cli(
            "task",
            "update",
            "task-1",
            "--owner",
            "",
            "--priority",
            "high",
            "--add-blocked-by",
            "task-2",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.server.calls[-1],
            (
                "PATCH",
                "/clawteam/openapi/team/demo/task/task-1",
                {
                    "owner": "",
                    "priority": "high",
                    "add_blocked_by": ["task-2"],
                    "caller": "board",
                    "force": False,
                },
            ),
        )

    def test_old_server_does_not_silently_ignore_creation_options(self):
        result = self.run_cli(
            "task", "create", "test", "--priority", "urgent", prefix="/old/api"
        )
        self.assertEqual(result.returncode, 1)
        self.assertTrue(all(call[0] == "GET" for call in self.server.calls))

    def test_message_file_and_spawn_use_http_only(self):
        with tempfile.TemporaryDirectory() as directory:
            content = Path(directory) / "message.txt"
            content.write_text("第一行\n$HOME `literal`", encoding="utf-8")
            result = self.run_cli(
                "message", "send", "worker", "--content-file", str(content)
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                self.server.calls[-1][1], "/clawteam/openapi/team/demo/messages"
            )
            self.assertEqual(
                self.server.calls[-1][2]["content"], "第一行\n$HOME `literal`"
            )
            request = Path(directory) / "spawn.json"
            payload = {"agent_name": "worker", "command": ["fake"], "repo": "/repo"}
            request.write_text(json.dumps(payload))
            result = self.run_cli("agent", "spawn", "--request-file", str(request))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                self.server.calls[-1],
                ("POST", "/clawteam/openapi/team/demo/agents/spawn", payload),
            )

    def test_reads_and_writes_all_use_openapi_key(self):
        for args in (("agents",), ("overview",), ("team",), ("events",)):
            with self.subTest(args=args):
                self.assertEqual(self.run_cli(*args).returncode, 0)
        self.assertTrue(self.server.auth)
        self.assertTrue(
            all(
                path.startswith("/clawteam/openapi/") and auth == "Bearer test-secret"
                for path, auth in self.server.auth
            )
        )

    def test_missing_key_does_not_send_a_request(self):
        with tempfile.TemporaryDirectory() as home:
            result = self.run_cli(
                "task", "create", "test", HOME=home, CLAWTEAM_BOARD_API_KEY=""
            )
            read = self.run_cli("overview", HOME=home, CLAWTEAM_BOARD_API_KEY="")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(read.returncode, 1)
        self.assertEqual(self.server.calls, [])

    def test_bad_key_never_falls_back_and_is_redacted(self):
        result = self.run_cli(
            "task", "create", "test", CLAWTEAM_BOARD_API_KEY="private-test-key"
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("401", result.stderr)
        self.assertNotIn("private-test-key", result.stderr + result.stdout)
        self.assertEqual(
            self.server.calls, [("GET", "/clawteam/openapi/capabilities", None)]
        )

    def test_key_file_and_explicit_api_url(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "key"
            key.write_text("test-secret\n", encoding="utf-8")
            result = self.run_cli(
                "--api-key-file",
                str(key),
                "--api-url",
                self.host + "/custom/openapi/",
                "capabilities",
                CLAWTEAM_BOARD_API_KEY="wrong-env-key",
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.server.auth, [("/custom/openapi/capabilities", "Bearer test-secret")]
        )

    def test_redirect_does_not_forward_key(self):
        result = self.run_cli(
            "--api-url", self.host + "/redirect/openapi", "capabilities"
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("302", result.stderr)
        self.assertEqual(len(self.server.calls), 1)
        self.assertNotIn("test-secret", result.stderr)


if __name__ == "__main__":
    unittest.main()
