"""Import structured prompt.yaml into Magpie Instructions before agents start."""

import os
import sys
from pathlib import Path

import yaml

from skills_bootstrap import Library


def read_instructions(path):
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or set(config) != {"instructions"}:
        raise ValueError("prompt.yaml 必须只包含 instructions 对象。")
    instructions = config["instructions"]
    if not isinstance(instructions, dict):
        raise TypeError("instructions 必须是对象。")
    if set(instructions) - {"shared", "agents", "extra"}:
        raise ValueError("instructions 只支持 shared、agents 和 extra。")
    if "shared" in instructions and not isinstance(instructions["shared"], str):
        raise TypeError("instructions.shared 必须是字符串。")
    if "agents" in instructions:
        agents = instructions["agents"]
        if not isinstance(agents, list) or any(
            not isinstance(agent, str) or not agent.strip() for agent in agents
        ):
            raise TypeError("instructions.agents 必须是字符串列表。")
    if "extra" in instructions:
        extra = instructions["extra"]
        if not isinstance(extra, dict) or any(
            not isinstance(agent, str) or not isinstance(text, str)
            for agent, text in extra.items()
        ):
            raise TypeError("instructions.extra 必须是 Agent 到文本的映射。")
    return instructions


def configure(path):
    instructions = read_instructions(path)
    if not instructions:
        return
    key = os.environ.get("MAGPIE_WEB_KEY", "").strip()
    if not key:
        key = Path.home().joinpath(".config/magpie/web.key").read_text().strip()
    library = Library(key)
    view = library.request("/api/library")
    agents = view.get("instructions", {}).get("agents", [])
    known = {agent["agent"] for agent in agents}
    requested = set(instructions.get("agents", [])) | set(instructions.get("extra", {}))
    if not requested <= known:
        raise ValueError("prompt.yaml 包含 Magpie Instructions 未识别的 Agent。")
    view = library.request("/api/library/instructions/save", instructions)
    result = view.get("result") if isinstance(view, dict) else None
    if not isinstance(result, dict):
        raise TypeError("Magpie Instructions 未返回保存结果。")
    if result.get("problems"):
        raise RuntimeError("Magpie Instructions 同步失败，请检查 Agent 指令文件。")
    print("prompt: 已导入 Magpie Instructions。", flush=True)


if __name__ == "__main__":
    try:
        configure(Path(sys.argv[1]))
    except (OSError, ValueError, TypeError, RuntimeError, yaml.YAMLError) as error:
        print(f"提示词启动配置失败：{error}", file=sys.stderr)
        sys.exit(1)
