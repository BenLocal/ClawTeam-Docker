# ClawTeam 上游 API 与 skill 扩展

核对日期：2026-10-28。上游 `main` 提交为 [`01198332ef9270c32c5460b8a178f964fc0df451`](https://github.com/HKUDS/ClawTeam/commit/01198332ef9270c32c5460b8a178f964fc0df451)，[`pyproject.toml`](https://github.com/HKUDS/ClawTeam/blob/01198332ef9270c32c5460b8a178f964fc0df451/pyproject.toml) 声明版本 0.3.0。以下是该提交的源码能力，不代表其他部署已经升级或接口兼容。本仓库 [skill](../../skills/clawteam/SKILL.md) 的现状见文末「后续状态」。

## Board HTTP 接口

上游 [路由实现](https://github.com/HKUDS/ClawTeam/blob/01198332ef9270c32c5460b8a178f964fc0df451/clawteam/board/server.py#L128-L190) 列出以下接口，路径不含部署时可能使用的反向代理前缀。

| 方法和路径 | 返回或操作 |
| --- | --- |
| `GET /api/overview` | 所有团队摘要 |
| `GET /api/team/{team}` | 团队完整快照 |
| `GET /api/events/{team}` | 周期性 SSE 团队快照；事件是完整快照，不是单条变更 |
| `POST /api/team/{team}/task` | 接受 `subject`、`description`、`owner`，返回任务 ID；不能设置优先级或依赖 |
| `GET /api/proxy?url=...` | 代理读取受限制的 GitHub 内容；只允许 HTTPS 和指定 GitHub 主机，无任务管理用途 |

团队快照包含 `team`、`members`、按状态分组的 `tasks`、`taskSummary`、`messages`、`cost`、`conflicts`。成员的 `inboxCount` 是邮箱未读数，不能据此断定进程存活；消息来自事件日志，最多取最近 200 条。费用来自记录的费用事件；冲突字段来自工作区文件重叠检测，不能当作已确认的 Git 合并冲突。采集费用、冲突或消息出错时，上游会吞掉异常并返回空值或空列表，空结果不能证明没有记录。见 [采集实现](https://github.com/HKUDS/ClawTeam/blob/01198332ef9270c32c5460b8a178f964fc0df451/clawteam/board/collector.py#L62-L190)。

## 仅 CLI 提供的操作

上游 [CLI 任务命令](https://github.com/HKUDS/ClawTeam/blob/01198332ef9270c32c5460b8a178f964fc0df451/clawteam/cli/commands.py#L2104-L2290) 支持创建时指定优先级和依赖，以及更新状态、负责人、描述、优先级和依赖。CLI 还支持 [消息发送、广播与接收](https://github.com/HKUDS/ClawTeam/blob/01198332ef9270c32c5460b8a178f964fc0df451/clawteam/cli/commands.py#L1756-L1912)、[启动 agent](https://github.com/HKUDS/ClawTeam/blob/01198332ef9270c32c5460b8a178f964fc0df451/clawteam/cli/commands.py#L3093)、[工作区检查与合并](https://github.com/HKUDS/ClawTeam/blob/01198332ef9270c32c5460b8a178f964fc0df451/clawteam/cli/commands.py#L3666-L3903)、团队成员管理与快照恢复。上述写操作没有对应的 Board HTTP 路由；若要从远程 skill 调用，需要另建受控服务端接口或使用部署端 CLI，不能假设 HTTP 接口存在。

## 后续状态

2026-10-28 起，BenLocal/ClawTeam `self` 分支在 Board 上增加了管理接口：`/api/` 供浏览器面板使用，`/openapi/` 供外部客户端以 Bearer Key 调用，覆盖任务创建（含优先级与依赖）和更新、消息发送与广播、Agent 启动与运行状态，以及概览、团队快照和 SSE 的只读访问。接口定义见该分支的 `docs/board-api.md`。

本仓库 skill 的每个命令对应一个 `/openapi/` 端点。曾考虑的客户端派生功能（`task wait`、`watch`、消息过滤、任务摘要等）没有保留，需要时直接处理 `team` 快照的 JSON。团队创建与删除、成员增删、工作区合并与清理仍只有 CLI。
