"""Pass runtime configuration to systemd without shell-parsing commands or keys."""

import json
import os
import pwd
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

from proxy_bootstrap import docker_environment

STATE = Path("/run/clawteam")
ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def write_environment(path, environment):
    with path.open("w", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        for name, value in sorted(environment.items()):
            if ENVIRONMENT_NAME.fullmatch(name):
                # EnvironmentFile supports quoted multiline values; $ is literal.
                escaped = (
                    value.replace("\\", "\\\\")
                    .replace('"', '\\"')
                    .replace("`", "\\`")
                    .replace("$", "\\$")
                )
                stream.write(f'{name}="{escaped}"\n')


def prepare(arguments):
    node = pwd.getpwnam("node")
    STATE.mkdir(mode=0o750, parents=True, exist_ok=True)
    os.chown(STATE, 0, node.pw_gid)
    os.chmod(STATE, 0o750)
    environment = dict(
        os.environ, HOME=node.pw_dir, USER=node.pw_name, LOGNAME=node.pw_name
    )
    write_environment(STATE / "agent.env", environment)
    write_environment(
        STATE / "docker.env",
        docker_environment(environment),
    )
    command = STATE / "command.json"
    command.write_text(
        json.dumps(
            {"cwd": os.getcwd(), "args": arguments or ["start"]}, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    os.chown(command, 0, node.pw_gid)
    command.chmod(0o640)


def agent():
    result = subprocess.run(
        ["docker", "info", "--format", "{{.ID}}"],
        capture_output=True,
        timeout=10,
        check=False,
    )
    if result.returncode:
        raise SystemExit("Docker 服务未就绪，请检查 systemctl status docker。")
    for _ in range(150):
        health = subprocess.run(
            ["magpie", "healthcheck"], capture_output=True, check=False, timeout=5
        )
        if health.returncode == 0:
            break
        time.sleep(0.2)
    else:
        raise SystemExit("Magpie 服务未就绪，请检查 systemctl status magpie。")
    command = json.loads((STATE / "command.json").read_text(encoding="utf-8"))
    os.chdir(command["cwd"])
    os.execvp("container-entrypoint", ["container-entrypoint", *command["args"]])


def magpie() -> None:
    key_file = Path.home() / ".config/magpie/web.key"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if not key_file.exists() or not key_file.read_text(encoding="utf-8").strip():
        with key_file.open("w", encoding="utf-8") as stream:
            os.chmod(key_file, 0o600)
            stream.write(secrets.token_hex(32) + "\n")
    os.environ["MAGPIE_WEB_KEY"] = key_file.read_text(encoding="utf-8").strip()
    base = os.environ.get("CLAWTEAM_WEB_URL") or "http://localhost:" + os.environ.get(
        "CLAWTEAM_WEB_PORT", "8080"
    )
    os.environ["MAGPIE_WEB_URL"] = base.rstrip("/") + "/magpie"
    os.execvp("magpie", ["magpie", "web", "--addr", "127.0.0.1:3430", "--no-open"])


if __name__ == "__main__":
    try:
        if sys.argv[1] == "prepare":
            prepare(sys.argv[2:])
        elif sys.argv[1] == "agent":
            agent()
        elif sys.argv[1] == "magpie":
            magpie()
        else:
            raise SystemExit("Expected prepare, agent or magpie")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise SystemExit(
            "systemd 启动配置失败，请检查 /run/clawteam 和 Docker 服务。"
        ) from None
