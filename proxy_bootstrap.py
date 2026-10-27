"""Pass runtime proxies to inner Docker containers and builds, preserving auth."""

import json
import os
from pathlib import Path


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
    for variable, key in (
        ("HTTP_PROXY", "httpProxy"),
        ("HTTPS_PROXY", "httpsProxy"),
        ("ALL_PROXY", "allProxy"),
        ("NO_PROXY", "noProxy"),
    ):
        value = os.environ.get(variable, "")
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
