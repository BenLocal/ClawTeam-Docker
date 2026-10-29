"""Import openbao.yaml into OpenBao, then run OpenBao Agent to render secret files.

Initialization and unsealing stay manual. This waits until OpenBao is unsealed
and the import token file exists, writes the declared KV secrets, grants a
read-only AppRole to the agent, and execs `bao agent` to render the files.
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

import yaml

ADDRESS = "http://127.0.0.1:8200"
MOUNT = "secret"
ROLE = "clawteam-agent"
SECRET_PATH = re.compile(r"[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*")
POLL_SECONDS = 10


def read_config(path):
    """Validate the whole file before touching OpenBao."""
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(config, dict) or set(config) - {"secrets", "files"}:
        raise ValueError("openbao.yaml 只支持 secrets 和 files。")
    secrets = config.get("secrets") or {}
    if not isinstance(secrets, dict):
        raise TypeError("secrets 必须是路径到键值的映射。")
    for name, data in secrets.items():
        # "." and ".." segments would resolve to other API endpoints in the URL.
        if (
            not isinstance(name, str)
            or not SECRET_PATH.fullmatch(name)
            or {".", ".."} & set(name.split("/"))
        ):
            raise ValueError(
                "secrets 的路径只能包含字母、数字、. _ - 和 /，且不能有 . 或 .. 段。"
            )
        if (
            not isinstance(data, dict)
            or not data
            or any(
                not isinstance(key, str) or not key or not isinstance(value, str)
                for key, value in data.items()
            )
        ):
            raise TypeError(f"secrets.{name} 必须是非空的字符串键值映射。")
    files = config.get("files") or []
    if not isinstance(files, list):
        raise TypeError("files 必须是列表。")
    paths = set()
    for item in files:
        if (
            not isinstance(item, dict)
            or set(item) != {"path", "template"}
            or not isinstance(item["path"], str)
            or not item["path"].startswith("/")
            or not isinstance(item["template"], str)
            or not item["template"].strip()
        ):
            raise TypeError("files 的每一项必须只包含绝对路径 path 和非空 template。")
        if item["path"] in paths:
            raise ValueError("files 的 path 不可重复。")
        paths.add(item["path"])
    return secrets, files


class Client:
    def __init__(self, address=ADDRESS, token=""):
        self.address = address
        self.token = token
        self.opener = build_opener(ProxyHandler({}))

    def call(self, method, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["X-Vault-Token"] = self.token
        request = Request(
            self.address + "/v1/" + path, data=body, headers=headers, method=method
        )
        try:
            with self.opener.open(request, timeout=15) as response:
                raw = response.read()
        except HTTPError as error:
            if error.code == 404 and method == "GET":
                return None
            # Error bodies can echo request values; report the status only.
            raise RuntimeError(f"OpenBao {method} {path} 返回 {error.code}") from None
        return json.loads(raw) if raw else {}


def health(client):
    """Return 'ready', or the reason OpenBao cannot be used yet."""
    try:
        client.opener.open(client.address + "/v1/sys/health", timeout=5).close()
        return "ready"
    except HTTPError as error:
        return {501: "未初始化", 503: "已封存", 429: "备用节点"}.get(
            error.code, f"状态 {error.code}"
        )
    except (URLError, OSError):
        return "未启动"


def wait_until(check, describe):
    last = None
    while True:
        state = check()
        if state == "ready":
            return
        if state != last:
            print(f"openbao: 等待{describe}（{state}）。", flush=True)
            last = state
        time.sleep(POLL_SECONDS)


def token_state(token_file):
    try:
        return "ready" if token_file.read_text(encoding="utf-8").strip() else "为空"
    except OSError:
        return "不存在"


def import_secrets(client, secrets):
    mounts = client.call("GET", "sys/mounts") or {}
    if MOUNT + "/" not in mounts.get("data", mounts):
        client.call(
            "POST", f"sys/mounts/{MOUNT}", {"type": "kv", "options": {"version": "2"}}
        )
        # A new KV v2 mount upgrades in the background and answers 400 until ready.
        for attempt in range(30):
            try:
                client.call("GET", f"{MOUNT}/config")
                break
            except RuntimeError:
                if attempt == 29:
                    raise
                time.sleep(1)
    for name, data in secrets.items():
        current = client.call("GET", f"{MOUNT}/data/{name}")
        if (current or {}).get("data", {}).get("data") != data:
            client.call("POST", f"{MOUNT}/data/{name}", {"data": data})
    rules = "\n".join(
        f'path "{MOUNT}/data/{name}" {{ capabilities = ["read"] }}' for name in secrets
    )
    client.call("PUT", f"sys/policies/acl/{ROLE}", {"policy": rules or "# none"})
    auth = client.call("GET", "sys/auth") or {}
    if "approle/" not in auth.get("data", auth):
        client.call("POST", "sys/auth/approle", {"type": "approle"})
    client.call(
        "POST",
        f"auth/approle/role/{ROLE}",
        {"token_policies": [ROLE], "token_ttl": "1h", "token_max_ttl": "24h"},
    )


def write_private(path, text):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(text)
    temporary.replace(path)


def agent_config(home, files):
    state = home / ".openbao/agent"
    return {
        "vault": {"address": ADDRESS},
        "auto_auth": {
            "method": [
                {
                    "type": "approle",
                    "config": {
                        "role_id_file_path": str(state / "role_id"),
                        "secret_id_file_path": str(state / "secret_id"),
                        "remove_secret_id_file_after_reading": False,
                    },
                }
            ]
        },
        "template": [
            {
                "contents": item["template"],
                "destination": item["path"],
                "perms": "0600",
                "create_dest_dirs": True,
            }
            for item in files
        ],
    }


def configure(config_path, token_file, home=None):
    """Import and prepare the agent; return the agent config path, or None."""
    secrets, files = read_config(config_path)
    if not secrets and not files:
        print("openbao: openbao.yaml 没有声明密钥或文件。", flush=True)
        return None
    client = Client()
    wait_until(lambda: health(client), " OpenBao 初始化并解封")
    wait_until(lambda: token_state(token_file), "导入令牌文件 " + str(token_file))
    client.token = token_file.read_text(encoding="utf-8").strip()
    import_secrets(client, secrets)
    print(f"openbao: 已导入 {len(secrets)} 个密钥路径。", flush=True)
    if not files:
        return None
    state = (home or Path.home()) / ".openbao/agent"
    role_id = client.call("GET", f"auth/approle/role/{ROLE}/role-id")["data"]["role_id"]
    write_private(state / "role_id", role_id)
    if not (state / "secret_id").exists():
        secret_id = client.call("POST", f"auth/approle/role/{ROLE}/secret-id")["data"][
            "secret_id"
        ]
        write_private(state / "secret_id", secret_id)
    path = state / "agent.json"
    write_private(path, json.dumps(agent_config(home or Path.home(), files), indent=2))
    return path


if __name__ == "__main__":
    if os.environ.get("CLAWTEAM_OPENBAO") != "1":
        sys.exit(0)
    token_path = Path(
        os.environ.get("CLAWTEAM_OPENBAO_TOKEN_FILE") or "/etc/clawteam/openbao.token"
    )
    try:
        config_path = configure(Path(sys.argv[1]), token_path)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RuntimeError,
        yaml.YAMLError,
    ) as error:
        print(f"OpenBao 导入失败：{error}", file=sys.stderr)
        sys.exit(1)
    if config_path is None:
        sys.exit(0)
    print("openbao: 启动 OpenBao Agent 渲染文件。", flush=True)
    os.execvp("bao", ["bao", "agent", f"-config={config_path}"])
