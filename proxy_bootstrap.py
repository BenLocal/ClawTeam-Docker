"""Pass runtime proxies to inner Docker containers and builds, preserving auth."""

import json
import os
from collections.abc import Mapping
from pathlib import Path


def docker_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """Normalize Docker proxies without changing the application's environment."""
    result = {}
    mirror = environment.get("MIRROR_HTTP_PROXY", "")
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        value = (
            mirror
            if mirror and name != "ALL_PROXY"
            else environment.get(name) or environment.get(name.lower(), "")
        )
        if value:
            result[name] = result[name.lower()] = value
    bypass = [
        item
        for item in (
            environment.get("NO_PROXY") or environment.get("no_proxy", "")
        ).split(",")
        if item
    ]
    for host in ("localhost", "127.0.0.1", "::1"):
        if host not in bypass:
            bypass.append(host)
    result["NO_PROXY"] = result["no_proxy"] = ",".join(bypass)
    return result


def download_environment() -> dict[str, str]:
    """Use the download proxy only for an install command's child process."""
    environment = dict(os.environ)
    mirror = environment.get("MIRROR_HTTP_PROXY", "")
    if mirror:
        environment.update(
            HTTP_PROXY=mirror, HTTPS_PROXY=mirror, http_proxy=mirror, https_proxy=mirror
        )
    return environment


def configure():
    path = (
        Path(os.environ.get("DOCKER_CONFIG", str(Path.home() / ".docker")))
        / "config.json"
    )
    config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(config, dict):
        raise TypeError("Docker config must be an object")
    if not isinstance(config.get("proxies", {}), dict):
        raise TypeError("Docker proxies must be an object")
    if not isinstance(config.get("proxies", {}).get("default", {}), dict):
        raise TypeError("Docker default proxy must be an object")
    proxies = config.setdefault("proxies", {}).setdefault("default", {})
    environment = docker_environment(os.environ)
    for variable, key in (
        ("HTTP_PROXY", "httpProxy"),
        ("HTTPS_PROXY", "httpsProxy"),
        ("ALL_PROXY", "allProxy"),
        ("NO_PROXY", "noProxy"),
    ):
        value = environment.get(variable, "")
        if value:
            proxies[key] = value
        else:
            proxies.pop(key, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("config.json.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        os.chmod(temporary, 0o600)
        json.dump(config, stream, indent=2)
        stream.write("\n")
    temporary.replace(path)


if __name__ == "__main__":
    try:
        configure()
    except (TypeError, ValueError, OSError):
        raise SystemExit(
            "Docker 代理配置失败，请检查 ~/.docker/config.json 的格式与读写权限。"
        ) from None
