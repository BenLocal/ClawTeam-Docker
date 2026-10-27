"""Preinstall a list of native Magpie plugin specs, preserving manual settings."""

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


def read_plugins(path):
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or set(config) != {"plugins"}:
        raise ValueError("plugin.yaml 必须只包含 plugins 列表。")
    plugins = config["plugins"]
    if not isinstance(plugins, list) or any(
        not isinstance(spec, str) or not spec.strip() or spec.startswith("-")
        for spec in plugins
    ):
        raise TypeError("plugins 必须是非空插件来源字符串的列表。")
    if len(set(plugins)) != len(plugins):
        raise ValueError("plugin.yaml 的插件来源不可重复。")
    return plugins


def configure(path):
    plugins = read_plugins(path)
    if not plugins:
        return
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    profile = config / "magpie/plugins.json"
    state_file = config / "clawteam-docker/plugin-sources.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    for index, source in enumerate(plugins, 1):
        installed = (
            json.loads(profile.read_text()).get("plugins", [])
            if profile.exists()
            else []
        )
        specs = {item["spec"] for item in installed}
        canonical = (
            str(Path(source).resolve())
            if source.startswith(("/", "./", "../"))
            else source.removeprefix("npm:")
        )
        if state.get(source) in specs:
            print(f"plugin: 第 {index} 个插件已安装，保留原配置。", flush=True)
            continue
        result = subprocess.run(
            ["magpie", "plugin", "add", source],
            capture_output=True,
            text=True,
            timeout=360,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                f"第 {index} 个插件安装失败，请检查来源、Git 凭据及网络。"
            )
        # Magpie resolves community aliases to the spec printed by its add command.
        resolved = next(
            (
                line.removeprefix("✓ added ").strip()
                for line in result.stdout.splitlines()
                if line.startswith("✓ added ")
            ),
            canonical,
        )
        if resolved:
            state[source] = resolved
            state_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = state_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(state))
            temporary.chmod(0o600)
            temporary.replace(state_file)
        print(f"plugin: 已安装第 {index} 个插件。", flush=True)


if __name__ == "__main__":
    try:
        configure(Path(sys.argv[1]))
    except (
        OSError,
        ValueError,
        TypeError,
        RuntimeError,
        subprocess.TimeoutExpired,
        yaml.YAMLError,
    ) as error:
        print(f"插件启动配置失败：{error}", file=sys.stderr)
        sys.exit(1)
