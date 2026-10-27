#!/usr/bin/env python3
"""Container integration check; uses fake providers, no live model credentials.

Run after ./clawteam.sh build: python3 tests/smoke.py
"""

import http.client
import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = f"clawteam-smoke-{os.getpid()}"
DIND = os.environ.get("CLAWTEAM_DIND") == "1"
FAKE_CLAUDE = """\
#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
with (Path.home() / "leader-starts.jsonl").open("a") as f:
    f.write(json.dumps({"pid": os.getpid(), "cwd": os.getcwd(), "args": sys.argv[1:], "skill": (Path.home() / ".claude/skills/startup-smoke/SKILL.md").read_text(), "instructions": (Path.home() / ".claude/CLAUDE.md").read_text()}) + "\\n")
while True:
    time.sleep(1)
"""
MOCK = """\
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
"""


def run(*args, env=None):
    return subprocess.check_output(args, env=env, text=True, stderr=subprocess.STDOUT)


def inside(*args):
    return run("docker", "exec", "--user", "node", NAME, *args)


def wait_for(check, message):
    for _ in range(100):
        try:
            if check():
                return
        except (OSError, subprocess.CalledProcessError):
            pass
        time.sleep(0.2)
    raise AssertionError(message)


def leader_starts():
    return [
        json.loads(line)
        for line in inside("cat", "/home/node/leader-starts.jsonl").splitlines()
    ]


with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
env = dict(os.environ, CLAWTEAM_CONTAINER=NAME, CLAWTEAM_WEB_PORT=str(port))
for key in (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "CLAWTEAM_ENV_FILE",
    "CLAWTEAM_MODEL",
    "CLAWTEAM_PROVIDERS_FILE",
    "CLAWTEAM_SKILLS_FILE",
    "CLAWTEAM_PROMPT_FILE",
    "CLAWTEAM_MCP_FILE",
    "CLAWTEAM_PLUGIN_FILE",
):
    env.pop(key, None)


def get(host, path="/clawteam/", cookie=None, stream=False):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(
        "GET",
        path,
        headers={"Host": f"{host}:{port}", **({"Cookie": cookie} if cookie else {})},
    )
    response = conn.getresponse()
    body = response.readline() if stream else response.read()
    result = response.status, dict(response.getheaders()), body
    conn.close()
    return result


try:
    with tempfile.TemporaryDirectory(prefix="clawteam smoke ") as directory:
        run("git", "init", directory)
        run(
            "git",
            "-C",
            directory,
            "-c",
            "user.name=Smoke",
            "-c",
            "user.email=smoke@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "initial",
        )
        Path(directory, "mock.py").write_text(MOCK)
        binaries = Path(directory, "bin")
        binaries.mkdir()
        fake_claude = binaries / "claude"
        fake_claude.write_text(FAKE_CLAUDE)
        fake_claude.chmod(0o755)
        providers = Path(directory, "providers.yaml")
        # JSON is valid YAML and keeps this host-side test standard-library only.
        startup_config = {
            "providers": [
                {
                    "id": name,
                    "url_env": f"SMOKE_{name.upper()}_URL",
                    "key_env": "SMOKE_KEY",
                    "models": ["mock-model"],
                }
                for name in ("first", "second")
            ],
            "groups": [
                {
                    "id": "coding",
                    "models": ["first/mock-model", "second/mock-model"],
                    "routing": "order",
                    "stays": "off",
                }
            ],
            "claude": {"model": "group/coding"},
        }
        providers.write_text(json.dumps(startup_config))
        env["CLAWTEAM_PROVIDERS_FILE"] = str(providers)
        skills = Path(directory, "skills")
        skills.mkdir()

        def add_skill(root, name, content):
            folder = root / name
            folder.mkdir(parents=True)
            (folder / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: Smoke fixture\n---\n{content}\n"
            )

        add_skill(skills, "startup-smoke", "original-skill")
        git_skills = Path(directory, "git-skills.git")
        git_skills.mkdir()
        run("git", "init", str(git_skills))

        def commit_skills():
            run("git", "-C", str(git_skills), "add", ".")
            run(
                "git",
                "-C",
                str(git_skills),
                "-c",
                "user.name=Smoke",
                "-c",
                "user.email=smoke@example.invalid",
                "commit",
                "-m",
                "skills",
            )

        add_skill(git_skills, "startup-git", "original-git-skill")
        commit_skills()
        skills_config = Path(directory, "skills.yaml")
        skill_sources = {
            "sources": [
                {"source": "/workspace/skills", "agents": ["claude"]},
                {"source": "file:///workspace/git-skills.git", "agents": ["claude"]},
            ]
        }
        skills_config.write_text(json.dumps(skill_sources))
        env["CLAWTEAM_SKILLS_FILE"] = str(skills_config)
        prompt_file = Path(directory, "prompt.yaml")
        custom_prompt = 'Custom prompt: "quotes", $literal, `literal`\n第二行。'
        prompt_config = {
            "instructions": {
                "shared": custom_prompt,
                "agents": ["claude"],
                "extra": {"claude": "Agent extra instructions"},
            }
        }
        prompt_file.write_text(json.dumps(prompt_config))
        env["CLAWTEAM_PROMPT_FILE"] = str(prompt_file)
        mcp_file = Path(directory, "mcp.yaml")
        mcp_config = {
            "servers": [
                {
                    "name": "startup-stdio",
                    "transport": "stdio",
                    "command": "python3",
                    "args": ["/workspace/example-mcp.py"],
                    "env": {"FIXTURE": "original"},
                    "agents": ["claude"],
                },
                {
                    "name": "startup-http",
                    "transport": "http",
                    "url": "http://127.0.0.1:9/mcp",
                    "headers": {"X-Fixture": "original"},
                    "agents": ["claude"],
                },
            ]
        }
        mcp_file.write_text(json.dumps(mcp_config))
        mcp_config["servers"][0]["install"] = {
            "command": [
                "python3",
                "-c",
                "from pathlib import Path; p=Path('/workspace/mcp-install-count'); p.write_text(p.read_text()+'x' if p.exists() else 'x')",
            ],
            "check": [
                "python3",
                "-c",
                "from pathlib import Path; raise SystemExit(0 if Path('/workspace/mcp-install-count').exists() else 1)",
            ],
        }
        mcp_file.write_text(json.dumps(mcp_config))
        env["CLAWTEAM_MCP_FILE"] = str(mcp_file)
        # GitHub's runner UID can differ from the image's UID 1000. This is a
        # disposable fixture: allow container writes and explicitly trust it.
        Path(directory).chmod(0o777)
        for path in Path(directory, ".git").rglob("*"):
            path.chmod(0o777 if path.is_dir() else 0o666)
        Path(directory, ".git").chmod(0o777)
        git_env = Path(directory, "test.env")
        git_env.write_text(
            "GIT_CONFIG_COUNT=2\nGIT_CONFIG_KEY_0=safe.directory\nGIT_CONFIG_VALUE_0=/workspace\n"
            "GIT_CONFIG_KEY_1=safe.directory\nGIT_CONFIG_VALUE_1=/workspace/git-skills.git\n"
            "PATH=/workspace/bin:/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n"
            "CLAWTEAM_LEADER_RESTART_DELAY=1\nSMOKE_KEY=test\n"
            "SMOKE_FIRST_URL=http://127.0.0.1:9101/v1\nSMOKE_SECOND_URL=http://127.0.0.1:9102/v1\n"
        )
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
        assert (
            f"localhost:{port}" in links
            and f"localhost:{port}/magpie/?k={key}" in links
        )
        inside("clawteam", "team", "spawn-team", "smoke", "-n", "leader")
        status, headers, body = get(
            "localhost", "/clawteam/api/events/smoke", stream=True
        )
        assert (
            status == 200
            and "text/event-stream" in headers["Content-Type"]
            and body.startswith(b"data:")
        )
        inside("tmux", "has-session", "-t", "clawteam")
        inside("nginx", "-t", "-c", "/etc/nginx/clawteam.conf")
        print(
            "PASS: one published port, both subpaths, Magpie auth, ClawTeam API/SSE, Leader tmux"
        )

        wait_for(lambda: len(leader_starts()) >= 1, "Leader did not launch")
        first_start = leader_starts()[-1]
        if DIND:

            def magpie_pid():
                return run(
                    "docker",
                    "exec",
                    "--user",
                    "root",
                    NAME,
                    "systemctl",
                    "show",
                    "magpie",
                    "-p",
                    "MainPID",
                    "--value",
                ).strip()

            previous_magpie = magpie_pid()
            run(
                "docker",
                "exec",
                "--user",
                "root",
                NAME,
                "systemctl",
                "kill",
                "--kill-whom=main",
                "--signal=KILL",
                "magpie",
            )
            wait_for(
                lambda: (
                    magpie_pid() not in ("0", previous_magpie)
                    and inside("magpie", "healthcheck") is not None
                ),
                "Magpie did not recover independently",
            )
            assert get("localhost", "/magpie/api/state", cookie=cookie)[0] == 200
            assert leader_starts()[-1]["pid"] == first_start["pid"]
            print(
                "PASS: systemd restarts Magpie independently and preserves its key and Leader"
            )
        assert first_start["cwd"] == "/workspace", first_start
        assert "--append-system-prompt" in first_start["args"]
        system_prompt = first_start["args"][
            first_start["args"].index("--append-system-prompt") + 1
        ]
        assert custom_prompt not in system_prompt
        assert custom_prompt in first_start["instructions"]
        assert "Agent extra instructions" in first_start["instructions"]
        assert "Leader 和所有 Worker 都必须在本容器运行" in system_prompt
        inside(
            "python3",
            "-c",
            "from pathlib import Path; p=Path.home()/'.claude/CLAUDE.md'; p.write_text(p.read_text()+'\\nManually maintained instruction\\n')",
        )
        assert "original-skill" in first_start["skill"], first_start
        library_before = json.loads(
            inside("cat", "/home/node/.config/magpie/library.json")
        )
        assert sorted(skill["name"] for skill in library_before["skills"]) == [
            "startup-git",
            "startup-smoke",
        ]
        assert "original-git-skill" in inside(
            "cat", "/home/node/.claude/skills/startup-git/SKILL.md"
        )
        assert (
            inside("readlink", "/home/node/.claude/skills/clawteam").strip()
            == "/opt/clawteam/skills/clawteam"
        )
        print(
            "PASS: Library installs skills before Leader and preserves the bundled ClawTeam skill"
        )
        claude_state = json.loads(inside("cat", "/home/node/.claude.json"))
        assert (
            claude_state["mcpServers"]["startup-stdio"]["env"]["FIXTURE"] == "original"
        )
        assert (
            claude_state["mcpServers"]["startup-http"]["url"]
            == "http://127.0.0.1:9/mcp"
        )
        inside(
            "python3",
            "-c",
            "import json; from pathlib import Path; p=Path.home()/'.claude.json'; d=json.loads(p.read_text()); d['mcpServers']['manual-mcp']={'type':'stdio','command':'/bin/true'}; p.write_text(json.dumps(d))",
        )
        inside(
            "python3",
            "-c",
            f"import os,signal; os.kill({first_start['pid']}, signal.SIGTERM)",
        )
        wait_for(
            lambda: len(leader_starts()) >= 2,
            "Leader did not restart after its process exited",
        )
        inside("tmux", "has-session", "-t", "clawteam")
        print(
            "PASS: configured Leader launches automatically and restarts after a process failure"
        )

        run("docker", "exec", "-d", NAME, "python3", "/workspace/mock.py")
        settings = json.loads(inside("cat", "/home/node/.claude/settings.json"))
        assert "group/coding" in json.dumps(settings)
        # Use the Anthropic endpoint Claude Code calls, with OpenAI-compatible fake upstreams.
        result = inside(
            "curl",
            "--fail-with-body",
            "-sS",
            "--max-time",
            "60",
            "http://127.0.0.1:3425/v1/messages",
            "-H",
            "Content-Type: application/json",
            "-H",
            "x-api-key: magpie",
            "-H",
            "anthropic-version: 2023-06-01",
            "-d",
            json.dumps(
                {
                    "model": "group/coding",
                    "max_tokens": 32,
                    "messages": [{"role": "user", "content": "test"}],
                }
            ),
        )
        assert "fallback-ok" in result, result
        calls = inside("cat", "/tmp/provider-calls")
        assert "9101" in calls and "9102" in calls, calls
        print(
            "PASS: Claude settings route to Magpie; first provider 429 -> second provider succeeds"
        )
        # docker start must re-apply changed config without duplicating providers.
        starts_before = len(leader_starts())
        inside("mkdir", "-p", "/home/node/.claude/skills/manual-smoke")
        inside(
            "python3",
            "-c",
            "from pathlib import Path; Path.home().joinpath('.claude/skills/manual-smoke/SKILL.md').write_text('manually installed skill')",
        )
        run("docker", "stop", NAME)
        startup_config["providers"][0].pop("key_env")
        startup_config["providers"][0]["key"] = "rotated-test-key"
        startup_config["claude"]["model"] = "second/mock-model"
        providers.write_text(json.dumps(startup_config))
        prompt_config["instructions"]["shared"] = "Updated prompt after restart"
        prompt_file.write_text(json.dumps(prompt_config))
        add_skill(skills, "startup-added", "new-after-restart")
        mcp_config["servers"][0]["env"]["FIXTURE"] = "updated"
        mcp_config["servers"][1]["headers"]["X-Fixture"] = "updated"
        mcp_file.write_text(json.dumps(mcp_config))
        (git_skills / "startup-git/SKILL.md").write_text(
            "---\nname: startup-git\ndescription: Updated\n---\nmust-not-auto-update\n"
        )
        add_skill(git_skills, "startup-git-added", "new-git-skill")
        commit_skills()
        collision = Path(directory, "collision")
        add_skill(collision, "startup-smoke", "must-not-replace")
        skill_sources["sources"].append(
            {"source": "/workspace/collision", "agents": ["claude"]}
        )
        skills_config.write_text(json.dumps(skill_sources))
        run("docker", "start", NAME)
        wait_for(lambda: get("localhost")[0] == 200, "Web did not restart")
        wait_for(
            lambda: len(leader_starts()) > starts_before,
            "Leader did not return after docker start",
        )
        saved_providers = json.loads(
            inside("cat", "/home/node/.config/magpie/providers.json")
        )
        assert [item["id"] for item in saved_providers["providers"]] == [
            "first",
            "second",
        ], saved_providers
        assert saved_providers["providers"][0]["key"] == "rotated-test-key"
        assert len(saved_providers["groups"]) == 1, saved_providers
        settings = json.loads(inside("cat", "/home/node/.claude/settings.json"))
        assert "second/mock-model" in settings["model"], settings
        assert inside("cat", "/home/node/.config/magpie/web.key").strip() == key
        library_after = json.loads(
            inside("cat", "/home/node/.config/magpie/library.json")
        )
        assert sorted(skill["name"] for skill in library_after["skills"]) == [
            "startup-added",
            "startup-git",
            "startup-git-added",
            "startup-smoke",
        ]
        assert "original-git-skill" in inside(
            "cat", "/home/node/.claude/skills/startup-git/SKILL.md"
        )
        assert "new-git-skill" in inside(
            "cat", "/home/node/.claude/skills/startup-git-added/SKILL.md"
        )
        assert "original-skill" in leader_starts()[-1]["skill"]
        instructions = leader_starts()[-1]["instructions"]
        assert "Updated prompt after restart" in instructions
        assert custom_prompt not in instructions
        assert "Manually maintained instruction" in instructions
        assert instructions.count("<!-- magpie:begin") == 1
        print(
            "PASS: prompt.yaml imports shared/extra Instructions before Leader, updates without duplicates and preserves user text"
        )
        claude_state = json.loads(inside("cat", "/home/node/.claude.json"))
        assert (
            claude_state["mcpServers"]["startup-stdio"]["env"]["FIXTURE"] == "updated"
        )
        assert (
            claude_state["mcpServers"]["startup-http"]["headers"]["X-Fixture"]
            == "updated"
        )
        assert claude_state["mcpServers"]["manual-mcp"]["command"] == "/bin/true"
        saved_library = json.loads(
            inside("cat", "/home/node/.config/magpie/library.json")
        )
        assert len(saved_library["mcp"]) == 2
        assert inside("cat", "/workspace/mcp-install-count") == "x"
        assert "install" not in next(
            server
            for server in saved_library["mcp"]
            if server["name"] == "startup-stdio"
        )
        print(
            "PASS: mcp.yaml installs stdio/HTTP definitions, updates by name and preserves manual MCP servers"
        )
        assert (
            inside("cat", "/home/node/.claude/skills/manual-smoke/SKILL.md")
            == "manually installed skill"
        )
        assert "new-after-restart" in inside(
            "cat", "/home/node/.claude/skills/startup-added/SKILL.md"
        )
        assert next(
            skill
            for skill in library_after["skills"]
            if skill["name"] == "startup-smoke"
        ) == next(
            skill
            for skill in library_before["skills"]
            if skill["name"] == "startup-smoke"
        )
        print(
            "PASS: restart adds new skills, skips name collisions and preserves existing Library metadata"
        )
        add_skill(git_skills, "startup-timer-added", "new-from-periodic-update")
        commit_skills()
        if DIND:
            run(
                "docker",
                "exec",
                "--user",
                "root",
                NAME,
                "systemctl",
                "is-active",
                "clawteam-skills-update.timer",
            )
            run(
                "docker",
                "exec",
                "--user",
                "root",
                NAME,
                "systemctl",
                "start",
                "clawteam-skills-update.service",
            )
            assert (
                run(
                    "docker",
                    "exec",
                    "--user",
                    "root",
                    NAME,
                    "systemctl",
                    "show",
                    "clawteam-skills-update.service",
                    "-p",
                    "Result",
                    "--value",
                ).strip()
                == "success"
            )
        else:
            inside(
                "python3",
                "/usr/local/lib/clawteam-docker/skills_bootstrap.py",
                "--update",
            )
        assert "must-not-auto-update" in inside(
            "cat", "/home/node/.claude/skills/startup-git/SKILL.md"
        )
        assert "new-from-periodic-update" in inside(
            "cat", "/home/node/.claude/skills/startup-timer-added/SKILL.md"
        )
        assert (
            inside("cat", "/home/node/.claude/skills/manual-smoke/SKILL.md")
            == "manually installed skill"
        )
        print(
            "PASS: periodic Git update refreshes existing skills and adds new ones without restarting Leader"
        )
        edited_path = "/home/node/.claude/skills/startup-git/SKILL.md"
        fetched_content = inside("cat", edited_path)
        leader_before_update = leader_starts()[-1]["pid"]
        write_skill = "import sys; from pathlib import Path; Path(sys.argv[1]).write_text(sys.argv[2])"
        inside(
            "python3",
            "-c",
            write_skill,
            edited_path,
            fetched_content + "\nlocal-edit\n",
        )
        if DIND:
            update_command = (
                "docker",
                "exec",
                "--user",
                "root",
                NAME,
                "systemctl",
                "start",
                "clawteam-skills-update.service",
            )
        else:
            update_command = (
                "docker",
                "exec",
                "--user",
                "node",
                NAME,
                "python3",
                "/usr/local/lib/clawteam-docker/skills_bootstrap.py",
                "--update",
            )
        try:
            run(*update_command)
        except subprocess.CalledProcessError:
            pass
        else:
            raise AssertionError(
                "Updating a locally edited skill should report failure"
            )
        assert "local-edit" in inside("cat", edited_path)
        assert leader_starts()[-1]["pid"] == leader_before_update
        inside("tmux", "has-session", "-t", "clawteam")
        inside("python3", "-c", write_skill, edited_path, fetched_content)
        print("PASS: update conflicts preserve local edits and leave Leader running")
        print(
            "PASS: docker start re-applies providers.yaml, rotates the key and model, and keeps provider IDs stable"
        )
        # Recreate on the same home volume to verify credentials, groups and model selection persist.
        run(str(ROOT / "clawteam.sh"), "stop", env=env)
        init_options = ["--init"]
        if DIND:
            init_options = [
                "--init=false",
                "--privileged",
                "--user",
                "root",
                "--cgroupns=private",
                "--stop-signal",
                "SIGRTMIN+3",
                "--tmpfs",
                "/run",
                "--tmpfs",
                "/tmp:mode=1777",
                "-e",
                "CLAWTEAM_DIND=1",
                "--mount",
                f"type=volume,source={NAME}-docker,target=/var/lib/docker",
            ]
        run(
            "docker",
            "run",
            "-d",
            *init_options,
            "--name",
            NAME,
            "-p",
            f"127.0.0.1:{port}:8080",
            "--env-file",
            str(git_env),
            "-e",
            f"CLAWTEAM_WEB_PORT={port}",
            "-e",
            "CLAWTEAM_MODEL=group/coding",
            "--mount",
            f"type=bind,source={directory},target=/workspace",
            "--mount",
            f"type=bind,source={providers},target=/etc/clawteam/providers.yaml,readonly",
            "--mount",
            f"type=bind,source={skills_config},target=/etc/clawteam/skills.yaml,readonly",
            "--mount",
            f"type=bind,source={prompt_file},target=/etc/clawteam/prompt.yaml,readonly",
            "--mount",
            f"type=bind,source={mcp_file},target=/etc/clawteam/mcp.yaml,readonly",
            "--mount",
            f"type=volume,source={NAME}-home,target=/home/node",
            env.get("CLAWTEAM_IMAGE", "clawteam-local:latest"),
        )
        wait_for(
            lambda: get("localhost")[0] == 200,
            "Default CMD did not start the Web service",
        )
        wait_for(
            lambda: "group/coding" in inside("magpie", "claude", "model"),
            "Environment model override not applied",
        )
        assert inside("cat", "/home/node/.config/magpie/web.key").strip() == key
        assert "coding" in inside("magpie", "groups")
        inside("tmux", "has-session", "-t", "clawteam")
        print(
            "PASS: default CMD auto-starts, environment model overrides YAML, and Magpie key/group persist"
        )
        # A template with an empty required key must keep Web available without
        # repeatedly calling an unauthenticated model. Filling it resumes on start.
        starts_before = len(leader_starts())
        run("docker", "stop", NAME)
        for provider in startup_config["providers"]:
            provider.pop("key_env", None)
            provider["key"] = ""
            provider["key_required"] = True
        providers.write_text(json.dumps(startup_config))
        run("docker", "start", NAME)
        wait_for(
            lambda: get("localhost")[0] == 200,
            "Empty-key template stopped the Web service",
        )
        wait_for(
            lambda: "等待填写" in inside("tmux", "capture-pane", "-pt", "clawteam"),
            "Leader did not wait for its required key",
        )
        assert len(leader_starts()) == starts_before, (
            "Leader ran without its required key"
        )
        run("docker", "stop", NAME)
        for provider in startup_config["providers"]:
            provider["key"] = "filled-test-key"
        providers.write_text(json.dumps(startup_config))
        run("docker", "start", NAME)
        wait_for(
            lambda: len(leader_starts()) > starts_before,
            "Filling the key did not resume Leader",
        )
        assert (
            inside(
                "bash", "-c", "test ! -e /tmp/clawteam-provider-pending; echo $?"
            ).strip()
            == "0"
        )
        print(
            "PASS: empty required keys keep Web available and pause Leader; filling the key resumes on start"
        )
except Exception as error:
    if isinstance(error, subprocess.CalledProcessError):
        print(error.output)
    print(run("docker", "logs", NAME))
    raise
finally:
    subprocess.run(
        ["docker", "rm", "-f", NAME],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    subprocess.run(
        ["docker", "volume", "rm", f"{NAME}-home"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if DIND:
        subprocess.run(
            ["docker", "volume", "rm", f"{NAME}-docker"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
