"""Apply the startup provider configuration before the gateway and Leader start."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import yaml

ID = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
APIS = {
    "openai": "url",
    "anthropic": "anthropic",
    "responses": "responses",
    "gemini": "gemini",
}
PENDING_PATH = Path("/tmp/clawteam-provider-pending")


def read_json(path):
    return json.loads(path.read_text()) if path.exists() else {}


def magpie(*args):
    try:
        result = subprocess.run(
            ["magpie", *args], capture_output=True, text=True, timeout=60, check=False
        )
    except subprocess.TimeoutExpired:
        raise ValueError(f"Magpie {args[0]} 配置超时") from None
    if result.returncode:
        # CLI errors can contain the API key from its arguments or upstream URL.
        raise ValueError(
            f"Magpie {args[0]} 配置失败，退出码 {result.returncode}；请检查 providers.yaml"
        )


def validate(config):
    if not isinstance(config, dict):
        raise TypeError("providers.yaml 必须是 YAML 对象")
    if set(config) - {"providers", "groups", "claude"}:
        raise ValueError("providers.yaml 包含未知顶层字段")
    providers = config.get("providers", [])
    groups = config.get("groups", [])
    if not isinstance(providers, list) or not isinstance(groups, list):
        raise TypeError("providers 和 groups 必须是列表")
    for entries, fields in (
        (
            providers,
            {"id", "api", "url", "url_env", "key", "key_env", "key_required", "models"},
        ),
        (groups, {"id", "models", "routing", "stays"}),
    ):
        seen = set()
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) - fields:
                raise ValueError("provider 或 group 格式错误，或包含未知字段")
            identifier = entry.get("id", "")
            if (
                not isinstance(identifier, str)
                or not ID.fullmatch(identifier)
                or identifier in seen
            ):
                raise ValueError(
                    "provider/group 的 id 必须唯一，且只包含小写字母、数字和连字符"
                )
            seen.add(identifier)
            models = entry.get("models")
            if (
                not isinstance(models, list)
                or not models
                or any(
                    not isinstance(model, str) or not model.strip() or "," in model
                    for model in models
                )
            ):
                raise ValueError(f"{identifier} 必须提供非空 models 列表")
    for entry in providers:
        if ("url" in entry) == ("url_env" in entry):
            raise ValueError("provider 必须设置 url 或 url_env 中的一个")
        if "url_env" in entry and (
            not isinstance(entry["url_env"], str) or entry["url_env"] not in os.environ
        ):
            raise ValueError(f"provider {entry['id']} 引用的 url_env 未设置")
        url = os.environ[entry["url_env"]] if "url_env" in entry else entry["url"]
        if not isinstance(url, str):
            raise TypeError("provider url 必须是字符串")
        parsed = urlsplit(url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("provider url 必须是无登录凭据的 HTTP(S) 地址")
        if (
            not isinstance(entry.get("api", "openai"), str)
            or entry.get("api", "openai") not in APIS
        ):
            raise ValueError("provider api 只支持 openai、anthropic、responses、gemini")
        if "key" in entry and "key_env" in entry:
            raise ValueError("key 与 key_env 只能设置一个")
        if "key_env" in entry:
            variable = entry["key_env"]
            if not isinstance(variable, str) or variable not in os.environ:
                raise ValueError(f"provider {entry['id']} 引用的 key_env 未设置")
        elif not isinstance(entry.get("key", ""), str):
            raise TypeError("provider key 必须是字符串，免认证时使用空字符串")
        if not isinstance(entry.get("key_required", False), bool):
            raise TypeError("key_required 必须是布尔值")
    for entry in groups:
        if not isinstance(entry.get("routing", "order"), str) or entry.get(
            "routing", "order"
        ) not in {
            "smart",
            "order",
            "rotate",
            "usage",
            "pace",
            "weight",
            "free",
            "fast",
        }:
            raise ValueError("group routing 不受支持")
        if not isinstance(entry.get("stays", "off"), str) or entry.get(
            "stays", "off"
        ) not in {"auto", "session", "turn", "off", "strict"}:
            raise ValueError('group stays 必须是字符串，例如 stays: "off"')
    claude = config.get("claude", {})
    if not isinstance(claude, dict) or set(claude) - {"model", "effort"}:
        raise ValueError("claude 只支持 model 和 effort 字段")
    if not isinstance(claude.get("model", ""), str):
        raise TypeError("claude.model 必须是字符串")
    if "effort" in claude and (
        not isinstance(claude["effort"], str)
        or claude["effort"] not in {"low", "medium", "high", "xhigh", "max"}
    ):
        raise ValueError("claude.effort 不受支持")
    return providers, groups, claude


def configure(path):
    providers, groups, claude = validate(
        yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    )
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    saved = read_json(config_home / "magpie/providers.json")
    existing = {provider["id"] for provider in saved.get("providers", [])}
    pending = []
    for entry in providers:
        identifier = entry["id"]
        url = os.environ[entry["url_env"]] if "url_env" in entry else entry["url"]
        key = (
            os.environ[entry["key_env"]] if "key_env" in entry else entry.get("key", "")
        )
        if entry.get("key_required") and not key.strip():
            pending.append(identifier)
            # Some vendors refuse an empty key even when only saving config.
            # This placeholder is never used by Leader: its supervisor waits.
            key = "clawteam-unconfigured"
        options = [
            f"{APIS[entry.get('api', 'openai')]}={url}",
            f"key={key}",
            "models=" + ",".join(entry["models"]),
        ]
        if identifier in existing:
            magpie("provider", "set", identifier, *options)
        else:
            magpie("provider", "add", identifier, f"id={identifier}", *options)
        print(f"已配置 Magpie provider: {identifier}", file=sys.stderr)
    for entry in groups:
        magpie(
            "group",
            "add",
            entry["id"],
            "models=" + ",".join(entry["models"]),
            "routing=" + entry.get("routing", "order"),
            "stays=" + entry.get("stays", "off"),
        )
        print(f"已配置 Magpie group: {entry['id']}", file=sys.stderr)
    model = os.environ.get("CLAWTEAM_MODEL") or claude.get("model")
    if not model:
        settings = read_json(Path.home() / ".claude/settings.json")
        if (
            settings.get("env", {})
            .get("ANTHROPIC_BASE_URL", "")
            .startswith("http://127.0.0.1:3425")
        ):
            model = settings.get("model")
    if model:
        magpie("claude", model)
        if "effort" in claude:
            magpie("claude", "effort", claude["effort"])
        if shutil.which("dsh"):
            # dsh Workers share the Leader's model; Magpie writes every dsh profile.
            magpie("dsh", model)
        # An explicitly mounted Git workspace can start on a configured API model
        # without the first-run subscription sign-in or workspace trust screens.
        state_path = Path.home() / ".claude.json"
        state = read_json(state_path)
        state["hasCompletedOnboarding"] = True
        project = state.setdefault("projects", {}).setdefault(os.getcwd(), {})
        project["hasTrustDialogAccepted"] = True
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        state_path.chmod(0o600)
        print(model)
    if pending:
        PENDING_PATH.write_text(", ".join(pending))
        print("等待填写 API Key: " + ", ".join(pending), file=sys.stderr)
    else:
        PENDING_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        configure(sys.argv[1])
    except yaml.YAMLError:
        # YAML parse errors quote their input, which may contain a provider key.
        print(
            "Magpie 初始化失败，请检查 providers.yaml 的格式、模型和凭据环境变量。",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    except (TypeError, ValueError, OSError) as error:
        print(f"Magpie 初始化失败: {error}", file=sys.stderr)
        raise SystemExit(1) from None
