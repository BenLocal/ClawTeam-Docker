import hashlib
import hmac
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

spec = importlib.util.spec_from_file_location(
    "bridge", Path(__file__).parents[1] / "integrations/vikunja/bridge.py"
)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "secret").write_text("s" * 64)
        self.config = {
            "vikunja_url": "http://example.test",
            "secret_file": str(root / "secret"),
            "queue_db": str(root / "queue.db"),
            "dispatch_command": ["fake"],
            "projects": {"7": {"team": "test", "leader": "leader"}},
        }
        self.path = root / "config.yaml"
        self.path.write_text(yaml.safe_dump(self.config))
        self.b = bridge.Bridge(self.path)
        self.payload = {
            "event_name": "task.comment.created",
            "data": {
                "comment": {"id": 42, "comment": "<p>/clawteam run</p>"},
                "task": {"id": 9, "project_id": 7, "title": "Test"},
            },
        }

    def send(self):
        raw = json.dumps(self.payload).encode()
        sig = hmac.new(b"s" * 64, raw, hashlib.sha256).hexdigest()
        return self.b.accept(raw, sig)

    def test_authentication(self):
        self.assertEqual(self.b.accept(b"{}", "invalid")[0], 401)

    def test_filters(self):
        for task_patch in [{"project_id": 8}, {"done": True}]:
            payload = json.loads(json.dumps(self.payload))
            payload["data"]["task"].update(task_patch)
            self.assertIsNone(bridge.route_event(self.config, payload))
        self.config["projects"]["7"]["label"] = "clawteam"
        self.assertIsNone(bridge.route_event(self.config, self.payload))
        self.payload["data"]["task"]["labels"] = [{"title": "clawteam"}]
        self.assertIsNotNone(bridge.route_event(self.config, self.payload))

    def test_durable_deduplication(self):
        self.assertEqual(self.send(), (202, "queued"))
        self.b = bridge.Bridge(self.path)
        self.payload["data"]["comment"]["id"] = 43
        self.assertIn("already", self.send()[1])
        with patch.object(bridge.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.b.work_once()
            self.b.work_once()
            self.assertEqual(run.call_count, 1)

    def test_retry_and_disable(self):
        self.send()
        with patch.object(bridge.subprocess, "run") as run:
            run.return_value.returncode = 1
            self.b.work_once()
        with self.b.db() as db:
            self.assertEqual(
                db.execute("SELECT state,attempts FROM jobs").fetchone(), ("pending", 1)
            )
            db.execute("UPDATE jobs SET retry_at=0")
        self.config["projects"]["7"]["enabled"] = False
        self.path.write_text(yaml.safe_dump(self.config))
        with patch.object(bridge.subprocess, "run") as run:
            self.b.work_once()
            run.assert_not_called()

    def test_only_standalone_new_comment_triggers(self):
        for text in [
            "/clawteam run",
            "<p>/clawteam&nbsp;run</p>",
            "<div> /clawteam run </div>",
        ]:
            self.payload["data"]["comment"]["comment"] = text
            self.assertIsNotNone(bridge.route_event(self.config, self.payload), text)
        for text in [
            "普通评论",
            "请执行 /clawteam run",
            "/clawteam run extra",
            "<blockquote>/clawteam run</blockquote>",
            "<pre><code>/clawteam run</code></pre>",
            "`/clawteam run`",
            "> /clawteam run",
            "<p>/clawteam run</p><p>extra</p>",
        ]:
            self.payload["data"]["comment"]["comment"] = text
            self.assertIsNone(bridge.route_event(self.config, self.payload), text)
        self.payload["data"]["comment"]["comment"] = "/clawteam run"
        for event in [
            "task.created",
            "task.updated",
            "task.comment.edited",
            "task.comment.deleted",
        ]:
            self.payload["event_name"] = event
            self.assertIsNone(bridge.route_event(self.config, self.payload), event)

    def test_yaml_numeric_project_key_and_custom_command(self):
        self.config["projects"] = {7: {"team": "test"}}
        self.config["trigger"] = {"command": "/agent start"}
        self.path.write_text(yaml.safe_dump(self.config))
        self.assertEqual(self.send()[0], 200)
        self.payload["data"]["comment"]["comment"] = "<p>/agent start</p>"
        self.assertEqual(self.send()[0], 202)

    def test_old_automatic_jobs_are_not_dispatched(self):
        self.send()
        with self.b.db() as db:
            job = json.loads(db.execute("SELECT payload FROM jobs").fetchone()[0])
            del job["comment_id"]
            db.execute("UPDATE jobs SET payload=?", (json.dumps(job),))
        with patch.object(bridge.subprocess, "run") as run:
            self.b.work_once()
            run.assert_not_called()
        with self.b.db() as db:
            self.assertEqual(
                db.execute("SELECT state FROM jobs").fetchone()[0], "ignored"
            )


if __name__ == "__main__":
    unittest.main()
