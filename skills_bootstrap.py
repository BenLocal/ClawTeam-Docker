"""Import configured sources through Magpie Library before starting the Leader."""

import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

BASE = "http://127.0.0.1:3430"


def read_sources(path):
    config = yaml.safe_load(path.read_text())
    if not isinstance(config, dict) or set(config) != {"sources"}:
        raise ValueError("skills.yaml 必须只包含 sources 列表。")
    sources = config["sources"]
    if not isinstance(sources, list):
        raise TypeError("skills.yaml 的 sources 必须是列表。")
    for index, item in enumerate(sources, 1):
        label = f"skills.yaml 来源 {index}"
        if not isinstance(item, dict) or set(item) != {"source", "agents"}:
            raise ValueError(f"{label} 必须包含 source 和 agents。")
        if not isinstance(item["source"], str) or not item["source"].strip():
            raise ValueError(f"{label} 的 source 必须是非空字符串。")
        agents = item["agents"]
        if (
            not isinstance(agents, list)
            or not agents
            or any(not isinstance(agent, str) or not agent.strip() for agent in agents)
        ):
            raise ValueError(f"{label} 的 agents 必须是非空字符串列表。")
    return sources


class Library:
    def __init__(self, key):
        # Internal requests must bypass deployment HTTP proxies.
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        )
        self.request("/?k=" + urllib.parse.quote(key, safe=""), login=True)

    def request(self, route, data=None, *, login=False):
        request = urllib.request.Request(
            BASE + route,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Content-Type": "application/json", "Origin": BASE},
        )
        try:
            with self.opener.open(request, timeout=180) as response:
                return None if login else json.load(response)
        except urllib.error.HTTPError as error:
            # Responses may contain private repository addresses or credentials.
            error.close()
            raise RuntimeError(
                f"Magpie Library 请求失败，HTTP {error.code}。"
            ) from None
        except (OSError, ValueError) as error:
            raise RuntimeError("Magpie Library 连接失败或返回了无效 JSON。") from error

    def change(self, route, data):
        view = self.request("/api/library/" + route, data)
        if not isinstance(view, dict) or not isinstance(view.get("result"), dict):
            raise TypeError("Magpie Library 未返回操作结果。")
        result = view["result"]
        if view.get("problems") or result.get("skipped"):
            raise RuntimeError(
                "Magpie Library 安装或同步存在冲突，请在 Library 页面检查。"
            )
        return result


def configure(path):
    sources = read_sources(path)
    if not sources:
        return
    key = os.environ.get("MAGPIE_WEB_KEY", "").strip()
    if not key:
        raise ValueError("导入 skills 需要 MAGPIE_WEB_KEY。")
    library = Library(key)
    view = library.request("/api/library")
    agents = view.get("agents") if isinstance(view, dict) else None
    if not isinstance(agents, list):
        raise TypeError("Magpie Library 未返回 Agent 列表。")
    known_agents = {agent["id"] for agent in agents}
    for index, item in enumerate(sources, 1):
        if not set(item["agents"]) <= known_agents:
            raise ValueError(f"skills.yaml 来源 {index} 包含 Magpie 未识别的 Agent。")
    for index, item in enumerate(sources, 1):
        probe = library.request("/api/library/skills/probe", {"source": item["source"]})
        candidates = probe.get("candidates") if isinstance(probe, dict) else None
        if not isinstance(candidates, list) or not candidates:
            raise RuntimeError(f"skills.yaml 来源 {index} 未找到技能。")
        paths = []
        for candidate in candidates:
            if (
                not isinstance(candidate, dict)
                or not isinstance(candidate.get("path"), str)
                or not isinstance(candidate.get("have"), bool)
            ):
                raise TypeError("Magpie Library 返回了无效扫描结果。")
            if candidate["have"]:
                print(
                    f"skills: 来源 {index} 已存在 {candidate.get('name', '')}，保留原配置。",
                    flush=True,
                )
            else:
                paths.append(candidate["path"])
        if paths:
            result = library.change(
                "skills/install",
                {"source": item["source"], "paths": paths, "agents": item["agents"]},
            )
            print(
                f"skills: 来源 {index} 已安装 {len(result.get('installed') or [])} 个技能。",
                flush=True,
            )
    library.change("all/sync", {})


if __name__ == "__main__":
    try:
        configure(Path(sys.argv[1]))
    except (OSError, ValueError, TypeError, RuntimeError, yaml.YAMLError) as error:
        print(f"技能启动配置失败：{error}", file=sys.stderr)
        sys.exit(1)
