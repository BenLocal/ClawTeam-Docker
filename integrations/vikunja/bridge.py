"""Signed Vikunja webhooks -> durable queue -> configured ClawTeam leader."""

import hashlib
import hmac
import json
import logging
import os
import sqlite3
import subprocess
import threading
import time
from contextlib import contextmanager
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class CommentText(HTMLParser):
    """Extract a standalone command, rejecting quotations and code examples."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.invalid = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag not in {"p", "div", "br", "span", "strong", "em", "b", "i"}:
            self.invalid = True
        if tag in {"p", "div", "br"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "div"}:
            self.parts.append(" ")

    def handle_data(self, text: str) -> None:
        self.parts.append(text)


def comment_command(text: object) -> str:
    if not isinstance(text, str):
        return ""
    parser = CommentText()
    parser.feed(text)
    return "" if parser.invalid else " ".join("".join(parser.parts).split())


def route_event(config: dict, payload: dict) -> dict | None:
    if payload.get("event_name") != "task.comment.created":
        return None
    data = payload.get("data") or {}
    comment = data.get("comment") or {}
    command = config.get("trigger", {}).get("command", "/clawteam run")
    if not command or comment_command(comment.get("comment")) != command:
        return None
    if type(comment.get("id")) is not int or comment["id"] <= 0:
        return None
    task = data.get("task", {})
    if (
        not isinstance(task, dict)
        or not isinstance(task.get("id"), int)
        or task["id"] <= 0
    ):
        return None
    route = config.get("projects", {}).get(str(task.get("project_id")))
    if not route or not route.get("enabled", True) or task.get("done"):
        return None
    if not route.get("team"):
        return None
    labels = {label.get("title") for label in (task.get("labels") or [])}
    if route.get("label") and route["label"] not in labels:
        return None
    return {
        "task": task,
        "team": route["team"],
        "leader": route.get("leader", "leader"),
        "trigger_command": command,
        "comment_id": comment["id"],
        "source": config["vikunja_url"].rstrip("/") + "/tasks/" + str(task["id"]),
    }


class Bridge:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path)
        self.config = self.load_config()
        self.db_path = self.config["queue_db"]
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.execute(
                'CREATE TABLE IF NOT EXISTS jobs (source TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT "pending", attempts INTEGER NOT NULL DEFAULT 0, retry_at REAL NOT NULL DEFAULT 0)'
            )

    def load_config(self) -> dict:
        config = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict) or not isinstance(config.get("projects"), dict):
            raise TypeError("Expected a YAML mapping with a projects mapping")
        config["projects"] = {
            str(key): value for key, value in config["projects"].items()
        }
        return config

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def accept(self, raw: bytes, signature: str) -> tuple[int, str]:
        config = self.load_config()
        secret = Path(config["secret_file"]).read_text(encoding="utf-8").strip()
        if len(secret) < 32:
            raise ValueError("Webhook secret must contain at least 32 characters")
        expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return 401, "invalid signature"
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return 400, "expected JSON object"
        job = route_event(config, payload)
        if not job:
            return 200, "ignored: command, event, project, label or completed task"
        with self.db() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO jobs(source,payload) VALUES (?,?)",
                (job["source"], json.dumps(job, ensure_ascii=False)),
            )
        return 202, "queued" if cursor.rowcount else "already queued or delivered"

    def work_once(self) -> None:
        with self.db() as db:
            row = db.execute(
                'SELECT source,payload,attempts FROM jobs WHERE state="pending" AND retry_at<=? ORDER BY rowid LIMIT 1',
                (time.time(),),
            ).fetchone()
        if not row:
            return
        source, payload, attempts = row
        try:
            config = self.load_config()
            job = json.loads(payload)
            # Old automatic-intake jobs must not bypass the comment-only gate.
            if not job.get("comment_id") or job.get("trigger_command") != config.get(
                "trigger", {}
            ).get("command", "/clawteam run"):
                with self.db() as db:
                    db.execute(
                        'UPDATE jobs SET state="ignored" WHERE source=?', (source,)
                    )
                return
            # Re-check routing before dispatch, so disabling a route stops queued work.
            route = config.get("projects", {}).get(
                str(job["task"].get("project_id")), {}
            )
            if (
                not route.get("enabled", True)
                or route.get("team") != job["team"]
                or route.get("leader", "leader") != job["leader"]
            ):
                with self.db() as db:
                    db.execute(
                        "UPDATE jobs SET retry_at=? WHERE source=?",
                        (time.time() + 30, source),
                    )
                return
            result = subprocess.run(
                config["dispatch_command"],
                check=False,
                input=payload,
                text=True,
                capture_output=True,
                timeout=45,
            )
            if result.returncode:
                raise RuntimeError(
                    "dispatch command failed with exit code " + str(result.returncode)
                )
            with self.db() as db:
                db.execute(
                    'UPDATE jobs SET state="delivered" WHERE source=?', (source,)
                )
            logger.info("Delivered %s", source)
        except Exception:
            logger.exception("Delivery failed for %s", source)
            with self.db() as db:
                db.execute(
                    "UPDATE jobs SET attempts=attempts+1,retry_at=? WHERE source=?",
                    (time.time() + min(300, 5 * 2 ** min(attempts, 6)), source),
                )

    def worker(self) -> None:
        while True:
            try:
                self.work_once()
            except Exception:
                logger.exception("Queue worker failed; will retry")
            time.sleep(2)


def serve(config_path: str | Path) -> None:
    bridge = Bridge(config_path)

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, message):
            data = json.dumps({"message": message}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self.reply(
                200 if self.path == "/health" else 404,
                "ok" if self.path == "/health" else "not found",
            )

        def do_POST(self):
            if self.path != "/hooks/vikunja":
                return self.reply(404, "not found")
            self.connection.settimeout(10)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 1024 * 1024:
                    return self.reply(413, "invalid body size")
                raw = self.rfile.read(length)
                status, message = bridge.accept(
                    raw, self.headers.get("X-Vikunja-Signature", "")
                )
                self.reply(status, message)
            except (ValueError, TypeError, AttributeError):
                self.reply(400, "invalid payload or configuration")
            except Exception:
                logger.exception("Webhook failed")
                self.reply(503, "temporarily unavailable")

    threading.Thread(target=bridge.worker, daemon=True).start()
    ThreadingHTTPServer(
        (bridge.config["listen_host"], bridge.config["listen_port"]), Handler
    ).serve_forever()


if __name__ == "__main__":
    import sys

    os.umask(0o077)
    logging.basicConfig(level=logging.INFO)
    serve(sys.argv[1])
