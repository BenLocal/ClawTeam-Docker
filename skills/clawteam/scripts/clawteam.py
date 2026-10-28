#!/usr/bin/env python3
"""Call a remote ClawTeam board API using only the Python standard library."""

import argparse
import json
import math
import os
import sys
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

DEFAULT_API = "http://172.31.169.115:28088/clawteam/openapi"
DEFAULT_TEAM = "courselab"
DEFAULT_KEY_FILE = Path.home() / ".config/clawteam/115-api.key"


class ClientError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    """Keep management credentials on the explicitly configured endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def positive_number(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("必须是大于 0 的有限数字")
    return number


class Client:
    def __init__(self, api_url, api_key, timeout=15, use_proxy=False):
        self.api_url = api_url.rstrip("/")
        if self.api_url.endswith("/api"):
            # Older settings name the browser API; external clients use /openapi.
            self.api_url = self.api_url[:-4] + "/openapi"
        parsed = urlsplit(self.api_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ClientError("API 地址必须是完整的 http:// 或 https:// URL")
        if parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ClientError("API 地址不能包含查询参数、片段或登录凭据")
        if not api_key or any(c.isspace() for c in api_key):
            raise ClientError(
                "OpenAPI 需要有效 Key；设置 CLAWTEAM_BOARD_API_KEY 或 --api-key-file"
            )
        self.api_key = api_key
        self.timeout = timeout
        handlers = [NoRedirect()] if use_proxy else [ProxyHandler({}), NoRedirect()]
        self.opener = build_opener(*handlers)

    def redact(self, text):
        return text.replace(self.api_key, "[REDACTED]")

    def open(self, path, payload=None, stream=False, method=None):
        body = (
            None
            if payload is None
            else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        )
        headers = {
            "Accept": "text/event-stream" if stream else "application/json",
            "Authorization": "Bearer " + self.api_key,
        }
        if body is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = Request(
            self.api_url + path, data=body, headers=headers, method=method
        )
        try:
            return self.opener.open(request, timeout=self.timeout)
        except HTTPError as exc:
            detail = exc.read(1000).decode("utf-8", errors="replace")
            raise ClientError(f"HTTP {exc.code}: {self.redact(detail)}") from exc

    def request(self, path, payload=None, expected=dict, method=None):
        with self.open(path, payload, method=method) as response:
            result = json.load(response)
        if isinstance(result, dict) and result.get("error"):
            raise ClientError(self.redact(str(result["error"])))
        if not isinstance(result, expected):
            raise ClientError("服务器响应类型不符，请检查 API 地址和版本")
        return result

    def require_feature(self, feature):
        try:
            capabilities = self.request("/capabilities")
        except ClientError as exc:
            raise ClientError(
                f"无法核实服务端能力 {feature}，未发送写请求；需支持管理 API 的版本。{exc}"
            ) from exc
        if feature not in capabilities.get("features", []):
            raise ClientError(f"服务端不支持 {feature}，未发送写请求")

    def events(self, team, count):
        with self.open("/events/" + quote(team, safe=""), stream=True) as response:
            content_type = response.headers.get_content_type()
            if content_type != "text/event-stream":
                raise ClientError(
                    f"服务器未返回 SSE，实际 Content-Type: {content_type}"
                )
            data = []
            received = 0
            for raw in response:
                line = raw.decode("utf-8").rstrip("\r\n")
                if line.startswith("data:"):
                    data.append(line[5:].removeprefix(" "))
                elif not line and data:
                    event = json.loads("\n".join(data))
                    if isinstance(event, dict) and event.get("error"):
                        raise ClientError(str(event["error"]))
                    print(json.dumps(event, ensure_ascii=False), flush=True)
                    data.clear()
                    received += 1
                    if count and received >= count:
                        return
            raise ClientError("SSE 连接已关闭，未收到要求数量的事件")


def nonnegative_int(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("必须大于或等于 0")
    return number


def emit(result, output=None):
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if output:
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="", flush=True)


def read_text(value, path):
    return path.read_text(encoding="utf-8") if path else value


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--api-url",
        default=os.getenv("CLAWTEAM_API_URL", DEFAULT_API),
        help="OpenAPI 根地址，需包含 /openapi；末尾为 /api 时自动改用 /openapi",
    )
    result.add_argument("--team", default=os.getenv("CLAWTEAM_TEAM", DEFAULT_TEAM))
    result.add_argument(
        "--api-key-file",
        type=Path,
        default=os.getenv("CLAWTEAM_API_KEY_FILE") or None,
        help="UTF-8 Key 文件；默认使用 CLAWTEAM_BOARD_API_KEY 或 ~/.config/clawteam/115-api.key",
    )
    result.add_argument(
        "--timeout",
        type=positive_number,
        default=15,
        help="连接及读取超时秒数，默认 15",
    )
    result.add_argument(
        "--use-proxy", action="store_true", help="使用环境代理；默认直接连接"
    )
    result.add_argument(
        "--output", type=Path, help="将单次查询结果保存为 UTF-8 JSON 文件"
    )
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("capabilities", help="GET /capabilities")
    commands.add_parser("overview", help="GET /overview")
    commands.add_parser("team", help="GET /team/{team}，团队、任务和消息快照")
    commands.add_parser("agents", help="GET /team/{team}/agents")
    event = commands.add_parser("events", help="GET /events/{team}，以 JSON Lines 输出")
    event.add_argument(
        "--count",
        type=nonnegative_int,
        default=1,
        help="事件条数，默认 1；0 表示持续订阅",
    )
    task = commands.add_parser("task", help="创建或更新任务")
    actions = task.add_subparsers(dest="action", required=True)
    create = actions.add_parser("create", help="POST /team/{team}/task")
    create.add_argument("subject")
    description = create.add_mutually_exclusive_group()
    description.add_argument("--description", "-d", default="")
    description.add_argument("--description-file", type=Path, help="UTF-8 描述文件")
    create.add_argument("--owner", default="", help="负责人，留空待 Leader 分配")
    create.add_argument("--priority", choices=("low", "medium", "high", "urgent"))
    create.add_argument(
        "--blocks", action="append", help="被本任务阻塞的任务 ID，可重复"
    )
    create.add_argument("--blocked-by", action="append", help="前置任务 ID，可重复")
    update = actions.add_parser("update", help="PATCH /team/{team}/task/{id}")
    update.add_argument("task_id")
    update.add_argument(
        "--status", choices=("pending", "in_progress", "completed", "blocked")
    )
    update.add_argument("--subject")
    update.add_argument("--owner")
    description = update.add_mutually_exclusive_group()
    description.add_argument("--description", "-d")
    description.add_argument("--description-file", type=Path)
    update.add_argument("--priority", choices=("low", "medium", "high", "urgent"))
    update.add_argument("--add-blocks", action="append")
    update.add_argument("--add-blocked-by", action="append")
    update.add_argument("--caller", default="board")
    update.add_argument("--force", action="store_true", help="显式覆盖任务锁")
    message = commands.add_parser("message", help="发送消息或广播")
    message_actions = message.add_subparsers(dest="action", required=True)
    for name, endpoint in (("send", "/messages"), ("broadcast", "/broadcast")):
        operation = message_actions.add_parser(
            name, help="POST /team/{team}" + endpoint
        )
        if name == "send":
            operation.add_argument("to")
        content = operation.add_mutually_exclusive_group(required=True)
        content.add_argument("--content")
        content.add_argument("--content-file", type=Path)
        operation.add_argument("--from", dest="sender", default="board")
        operation.add_argument("--key")
    agent = commands.add_parser("agent", help="启动 Agent")
    agent_actions = agent.add_subparsers(dest="action", required=True)
    spawn = agent_actions.add_parser("spawn", help="POST /team/{team}/agents/spawn")
    spawn.add_argument(
        "--request-file", type=Path, required=True, help="UTF-8 JSON 启动参数对象"
    )
    return result


def main(argv=None):
    arguments = parser()
    args = arguments.parse_args(argv)
    if not args.team.strip():
        arguments.error("团队名称不能为空")
    if args.command == "task" and args.action == "create" and not args.subject.strip():
        arguments.error("任务标题不能为空")
    if args.output and args.command == "events":
        arguments.error("流式命令请使用 stdout 重定向，不能使用 --output")
    update_fields = (
        "status",
        "subject",
        "owner",
        "description",
        "priority",
        "add_blocks",
        "add_blocked_by",
    )
    if (
        args.command == "task"
        and args.action == "update"
        and args.description_file is None
        and not any(getattr(args, name) is not None for name in update_fields)
    ):
        arguments.error("task update 至少需要一项修改")
    writing = args.command in ("task", "message", "agent")
    try:
        api_key = os.getenv("CLAWTEAM_BOARD_API_KEY", "").strip()
        if args.api_key_file:
            api_key = args.api_key_file.expanduser().read_text(encoding="utf-8").strip()
        elif not api_key and DEFAULT_KEY_FILE.is_file():
            api_key = DEFAULT_KEY_FILE.read_text(encoding="utf-8").strip()
        client = Client(args.api_url, api_key, args.timeout, args.use_proxy)
        team_path = "/team/" + quote(args.team, safe="")
        if args.command == "events":
            client.events(args.team, args.count)
            return 0
        if args.command == "capabilities":
            result = client.request("/capabilities")
        elif args.command == "overview":
            result = client.request("/overview", expected=list)
        elif args.command == "team":
            result = client.request(team_path)
        elif args.command == "agents":
            client.require_feature("agent_list")
            result = client.request(team_path + "/agents")
        elif args.command == "agent":
            payload = json.loads(args.request_file.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ClientError("启动参数必须是 JSON 对象")
            client.require_feature("agent_spawn")
            result = client.request(team_path + "/agents/spawn", payload)
        elif args.command == "message":
            content = read_text(args.content, args.content_file)
            if not content.strip():
                raise ClientError("消息内容不能为空")
            payload = {"from": args.sender, "content": content}
            if args.key is not None:
                payload["key"] = args.key
            if args.action == "send":
                payload["to"] = args.to
            client.require_feature("message_" + args.action)
            result = client.request(
                team_path + ("/messages" if args.action == "send" else "/broadcast"),
                payload,
            )
        elif args.action == "update":
            payload = {
                name: getattr(args, name)
                for name in update_fields
                if getattr(args, name) is not None
            }
            if args.description_file:
                payload["description"] = read_text(None, args.description_file)
            payload.update(caller=args.caller, force=args.force)
            client.require_feature("task_update")
            result = client.request(
                team_path + "/task/" + quote(args.task_id, safe=""),
                payload,
                method="PATCH",
            )
        else:
            payload = {
                "subject": args.subject,
                "description": read_text(args.description, args.description_file),
                "owner": args.owner,
            }
            payload.update(
                {
                    key: getattr(args, key)
                    for key in ("priority", "blocks", "blocked_by")
                    if getattr(args, key) is not None
                }
            )
            client.require_feature("task_create_options")
            result = client.request(team_path + "/task", payload)
            if result.get("status") != "ok" or not result.get("task_id"):
                raise ClientError("创建响应缺少成功状态或 task_id")
        emit(result, args.output)
        return 0
    except (ClientError, URLError, OSError, ValueError, HTTPException) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        if writing:
            print(
                "写请求未自动重试。若请求已发出，服务器可能已执行，请先查询任务、消息或 Agent 状态再决定是否重试。",
                file=sys.stderr,
            )
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
