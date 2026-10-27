"""Install named MCP server definitions through Magpie Library."""

import hashlib
import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

import yaml

from proxy_bootstrap import download_environment
from skills_bootstrap import Library

FIELDS = {
    "name",
    "transport",
    "command",
    "args",
    "env",
    "url",
    "headers",
    "agents",
    "install",
}


def read_servers(path):
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or set(config) != {"servers"}:
        raise ValueError("mcp.yaml 必须只包含 servers 列表。")
    servers = config["servers"]
    if not isinstance(servers, list):
        raise TypeError("servers 必须是列表。")
    names = set()
    for server in servers:
        if not isinstance(server, dict) or set(server) - FIELDS:
            raise ValueError("MCP 配置含未知字段。")
        for field in ("name", "transport"):
            if not isinstance(server.get(field), str) or not server[field].strip():
                raise ValueError(f"MCP {field} 必须是非空字符串。")
        if server["name"] in names:
            raise ValueError("MCP 名称不可重复。")
        names.add(server["name"])
        if "install" in server:
            install = server["install"]
            if not isinstance(install, dict) or set(install) != {"command", "check"}:
                raise ValueError("MCP install 必须包含 command 和 check 参数列表。")
            for command in install.values():
                if (
                    not isinstance(command, list)
                    or not command
                    or any(not isinstance(arg, str) for arg in command)
                    or not command[0].strip()
                ):
                    raise TypeError("MCP 安装和检查命令必须是非空字符串参数列表。")
        for field in ("agents", "args"):
            value = server.get(field, [] if field == "args" else None)
            if not isinstance(value, list) or any(
                not isinstance(item, str) or not item.strip() for item in value
            ):
                raise TypeError(f"MCP {field} 必须是字符串列表。")
        for field in ("env", "headers"):
            value = server.get(field, {})
            if not isinstance(value, dict) or any(
                not isinstance(key, str) or not key.strip() or not isinstance(item, str)
                for key, item in value.items()
            ):
                raise TypeError(f"MCP {field} 必须是字符串映射。")
        if server["transport"] == "stdio":
            if (
                not isinstance(server.get("command"), str)
                or not server["command"].strip()
                or "url" in server
                or "headers" in server
            ):
                raise ValueError("stdio MCP 需要 command，不能配置 url 或 headers。")
        elif server["transport"] in {"http", "sse"}:
            url = server.get("url")
            if (
                not isinstance(url, str)
                or urllib.parse.urlsplit(url).scheme not in {"http", "https"}
                or not urllib.parse.urlsplit(url).netloc
                or set(server) & {"command", "args", "env"}
            ):
                raise ValueError(
                    "远程 MCP 需要 HTTP(S) url，不能配置 command、args 或 env。"
                )
        else:
            raise ValueError("MCP transport 只支持 stdio、http 或 sse。")
    return servers


def run_command(command, timeout):
    try:
        return subprocess.run(
            command,
            capture_output=True,
            timeout=timeout,
            check=False,
            env=download_environment(),
        ).returncode
    except FileNotFoundError:
        return 127
    except subprocess.TimeoutExpired:
        raise RuntimeError("MCP 依赖安装或检查超时。") from None


def install_server(server):
    install = server.get("install")
    if install is None:
        return
    fingerprint = hashlib.sha256(
        json.dumps(install, sort_keys=True).encode()
    ).hexdigest()
    directory = (
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        / "clawteam-docker/mcp-installs"
    )
    filename = hashlib.sha256(server["name"].encode()).hexdigest() + ".json"
    state_file = directory / filename
    saved = json.loads(state_file.read_text()) if state_file.exists() else {}
    ready = run_command(install["check"], 60) == 0
    if ready and saved.get("fingerprint") == fingerprint:
        return
    if run_command(install["command"], 600) or run_command(install["check"], 60):
        raise RuntimeError("MCP 依赖安装失败或安装后检查未通过。")
    directory.mkdir(parents=True, exist_ok=True)
    temporary = state_file.with_suffix(".tmp")
    temporary.write_text(json.dumps({"fingerprint": fingerprint}))
    temporary.chmod(0o600)
    temporary.replace(state_file)
    print("mcp: 依赖已安装并通过检查。", flush=True)


def configure(path):
    servers = read_servers(path)
    if not servers:
        return
    key = os.environ.get("MAGPIE_WEB_KEY", "").strip()
    if not key:
        key = Path.home().joinpath(".config/magpie/web.key").read_text().strip()
    library = Library(key)
    view = library.request("/api/library")
    known = {agent["id"] for agent in view.get("agents", [])}
    if any(not set(server["agents"]) <= known for server in servers):
        raise ValueError("mcp.yaml 包含 Magpie 未识别的 Agent。")
    names = {server["name"] for server in view.get("servers", [])}
    for index, server in enumerate(servers, 1):
        install_server(server)
        library.change(
            "servers/save",
            {
                "old": server["name"] if server["name"] in names else "",
                "server": {
                    key: value for key, value in server.items() if key != "install"
                },
            },
        )
        names.add(server["name"])
        print(f"mcp: 已配置第 {index} 个服务。", flush=True)


if __name__ == "__main__":
    try:
        configure(Path(sys.argv[1]))
    except (OSError, ValueError, TypeError, RuntimeError, yaml.YAMLError) as error:
        print(f"MCP 启动配置失败：{error}", file=sys.stderr)
        sys.exit(1)
