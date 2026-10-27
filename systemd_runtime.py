"""Pass runtime configuration to systemd without shell-parsing commands or keys."""

import json
import os
import pwd
import re
import subprocess
import sys
from pathlib import Path

STATE = Path("/run/clawteam")
ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
PROXY_VARIABLES = {
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "NO_PROXY",
    "no_proxy",
    "ALL_PROXY",
    "all_proxy",
}


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
        {key: value for key, value in environment.items() if key in PROXY_VARIABLES},
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
    command = json.loads((STATE / "command.json").read_text(encoding="utf-8"))
    os.chdir(command["cwd"])
    os.execvp("container-entrypoint", ["container-entrypoint", *command["args"]])


if __name__ == "__main__":
    try:
        if sys.argv[1] == "prepare":
            prepare(sys.argv[2:])
        elif sys.argv[1] == "agent":
            agent()
        else:
            raise SystemExit("Expected prepare or agent")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise SystemExit(
            "systemd 启动配置失败，请检查 /run/clawteam 和 Docker 服务。"
        ) from None
