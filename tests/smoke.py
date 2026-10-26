#!/usr/bin/env python3
"""Container integration check; uses fake providers, no live model credentials.

Run after ./clawteam.sh build: python3 tests/smoke.py
"""
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
NAME = f"clawteam-smoke-{os.getpid()}"
MOCK = '''\
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import json
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        with open("/tmp/provider-calls", "a") as f: f.write(str(self.server.server_port) + "\\n")
        if self.server.server_port == 9101:
            status, body = 429, {"error": {"message": "quota exceeded", "type": "rate_limit_error"}}
        else:
            status, body = 200, {"id": "mock", "object": "chat.completion", "model": "mock-model", "choices": [{"index": 0, "message": {"role": "assistant", "content": "fallback-ok"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
        if status == 200 and request.get("stream"):
            chunks = [
                {"id": "mock", "object": "chat.completion.chunk", "model": "mock-model", "choices": [{"index": 0, "delta": {"role": "assistant", "content": "fallback-ok"}, "finish_reason": None}]},
                {"id": "mock", "object": "chat.completion.chunk", "model": "mock-model", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
            ]
            data = ("".join("data: " + json.dumps(chunk) + "\\n\\n" for chunk in chunks) + "data: [DONE]\\n\\n").encode()
            content_type = "text/event-stream"
        else:
            data = json.dumps(body).encode()
            content_type = "application/json"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
for port in (9101, 9102):
    Thread(target=ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever, daemon=True).start()
import time
time.sleep(300)
'''


def run(*args, env=None):
    return subprocess.check_output(args, env=env, text=True, stderr=subprocess.STDOUT)


def inside(*args):
    return run("docker", "exec", NAME, *args)


with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
env = dict(os.environ, CLAWTEAM_CONTAINER=NAME, CLAWTEAM_WEB_PORT=str(port))
for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
            "CLAWTEAM_ENV_FILE", "CLAWTEAM_MODEL"):
    env.pop(key, None)


def get(host, path="/clawteam/", cookie=None, stream=False):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", path, headers={"Host": f"{host}:{port}", **({"Cookie": cookie} if cookie else {})})
    response = conn.getresponse()
    body = response.readline() if stream else response.read()
    result = response.status, dict(response.getheaders()), body
    conn.close()
    return result


try:
    with tempfile.TemporaryDirectory(prefix="clawteam smoke ") as directory:
        run("git", "init", directory)
        run("git", "-C", directory, "-c", "user.name=Smoke", "-c", "user.email=smoke@example.invalid",
            "commit", "--allow-empty", "-m", "initial")
        Path(directory, "mock.py").write_text(MOCK)
        # GitHub's runner UID can differ from the image's UID 1000. This is a
        # disposable fixture: allow container writes and explicitly trust it.
        Path(directory).chmod(0o777)
        for path in Path(directory, ".git").rglob("*"):
            path.chmod(0o777 if path.is_dir() else 0o666)
        Path(directory, ".git").chmod(0o777)
        git_env = Path(directory, "test.env")
        git_env.write_text("GIT_CONFIG_COUNT=1\nGIT_CONFIG_KEY_0=safe.directory\nGIT_CONFIG_VALUE_0=/workspace\n")
        env["CLAWTEAM_ENV_FILE"] = str(git_env)
        print(run(str(ROOT / "clawteam.sh"), "start", directory, env=env).strip())
        for _ in range(50):
            try:
                if get("localhost")[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(0.2)
        status, _, body = get("localhost")
        assert status == 200 and b"ClawTeam" in body
        assert get("localhost", "/clawteam/api/overview")[0] == 200
        assert get("localhost", "/clawteam")[1]["Location"] == "/clawteam/"
        assert get("localhost", "/magpie?k=test")[1]["Location"] == "/magpie/?k=test"
        assert get("localhost", "/api/overview")[0] == 404
        assert b'data-prefix="/clawteam"' in body
        assert get("localhost", "/magpie/")[0] == 401
        key = inside("cat", "/home/node/.config/magpie/web.key").strip()
        status, headers, body = get("localhost", f"/magpie/?k={key}")
        assert status in (200, 302, 303), (status, body)
        assert headers["Location"] == "/magpie/", headers
        assert "Path=/magpie/" in headers["Set-Cookie"]
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, _, body = get("localhost", "/magpie/", cookie=cookie)
        assert status == 200 and b'data-prefix="/magpie"' in body
        assert get("localhost", "/magpie/app.js", cookie=cookie)[0] == 200
        assert get("localhost", "/magpie/api/state", cookie=cookie)[0] == 200
        links = run(str(ROOT / "clawteam.sh"), "web", env=env)
        assert f"localhost:{port}" in links and f"localhost:{port}/magpie/?k={key}" in links
        inside("clawteam", "team", "spawn-team", "smoke", "-n", "leader")
        status, headers, body = get("localhost", "/clawteam/api/events/smoke", stream=True)
        assert status == 200 and "text/event-stream" in headers["Content-Type"] and body.startswith(b"data:")
        inside("tmux", "has-session", "-t", "clawteam")
        inside("nginx", "-t", "-c", "/etc/nginx/clawteam.conf")
        print("PASS: one published port, both subpaths, Magpie auth, ClawTeam API/SSE, Leader tmux")

        run("docker", "exec", "-d", NAME, "python3", "/workspace/mock.py")
        for name, mock_port in (("first", 9101), ("second", 9102)):
            inside("magpie", "provider", "add", name, f"url=http://127.0.0.1:{mock_port}/v1", "key=test", "models=mock-model")
        inside("magpie", "group", "add", "coding", "models=first/mock-model,second/mock-model", "routing=order", "stays=off")
        inside("magpie", "claude", "group/coding")
        settings = json.loads(inside("cat", "/home/node/.claude/settings.json"))
        assert "group/coding" in json.dumps(settings)
        # Use the Anthropic endpoint Claude Code calls, with OpenAI-compatible fake upstreams.
        result = inside("curl", "--fail-with-body", "-sS", "--max-time", "60", "http://127.0.0.1:3425/v1/messages",
                        "-H", "Content-Type: application/json", "-H", "x-api-key: magpie",
                        "-H", "anthropic-version: 2023-06-01", "-d", json.dumps({
                            "model": "group/coding", "max_tokens": 32,
                            "messages": [{"role": "user", "content": "test"}]}))
        assert "fallback-ok" in result, result
        calls = inside("cat", "/tmp/provider-calls")
        assert "9101" in calls and "9102" in calls, calls
        print("PASS: Claude settings route to Magpie; first provider 429 -> second provider succeeds")
        # Recreate on the same home volume to verify credentials, groups and model selection persist.
        run(str(ROOT / "clawteam.sh"), "stop", env=env)
        env["CLAWTEAM_MODEL"] = "group/coding"
        run(str(ROOT / "clawteam.sh"), "start", directory, env=env)
        assert inside("cat", "/home/node/.config/magpie/web.key").strip() == key
        assert "coding" in inside("magpie", "groups")
        inside("tmux", "has-session", "-t", "clawteam")
        print("PASS: model-selected restart and persistent Magpie key/group")
except Exception as error:
    if isinstance(error, subprocess.CalledProcessError):
        print(error.output)
    print(run("docker", "logs", NAME))
    raise
finally:
    subprocess.run(["docker", "rm", "-f", NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["docker", "volume", "rm", f"{NAME}-home"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
