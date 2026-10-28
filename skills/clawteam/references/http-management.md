# HTTP 管理命令

以下命令使用 `scripts/clawteam.py`，与查询命令一样走 `/openapi/` 并携带 Bearer Key。先运行 `capabilities` 查看 `features`。服务端未升级或未配置 Key 时明确报告，不通过 `/api`、ah、SSH 或远端 shell 绕行。

```bash
python3 scripts/clawteam.py capabilities
python3 scripts/clawteam.py --team courselab task create '运行测试' --owner tester --priority high --blocked-by BUILD_ID
python3 scripts/clawteam.py --team courselab task update TASK_ID --status in_progress --owner developer
python3 scripts/clawteam.py --team courselab task update TASK_ID --priority urgent --add-blocked-by PREVIOUS_ID
python3 scripts/clawteam.py --team courselab task update TASK_ID --description-file /tmp/task-description.txt
python3 scripts/clawteam.py --team courselab message send developer --content-file /tmp/message.txt --from coordinator
python3 scripts/clawteam.py --team courselab message broadcast --content '共同说明' --from coordinator
python3 scripts/clawteam.py --team courselab agents
python3 scripts/clawteam.py --team courselab agent spawn --request-file /tmp/spawn.json
```

`--blocked-by`、`--blocks`、`--add-blocked-by` 和 `--add-blocks` 每次传一个任务 ID，可重复。`--owner ''` 清空负责人；`--description ''` 清空描述。`--caller` 默认 `board`，用于任务锁协调。只有明确需要覆盖锁时使用 `--force`。发送者使用实际协调身份，不冒充用户或已有成员。

更新走 `PATCH /openapi/team/{team}/task/{id}`，发送和广播走 `/messages`、`/broadcast`，启动走 `/agents/spawn`。JSON 正文由脚本编码，多行文本不会经过 shell 展开。写请求不自动重试；超时后先查询任务、消息或 Agent 状态，确认是否已经执行。

## 启动参数

`spawn.json` 是 JSON 对象，例如：

```json
{
  "agent_name": "reviewer",
  "backend": "tmux",
  "profile": "configured-profile",
  "repo": "/absolute/server/repository",
  "task": "审阅待处理改动",
  "workspace": true,
  "skip_permissions": false,
  "keepalive": true
}
```

`profile` 必须已在服务端配置，也可以用 `command` 字符串数组指定实际程序及参数。`repo` 属于服务端，必须是已存在的绝对目录；`workspace: true` 还要求它是 Git 仓库。后端支持 `tmux`、`subprocess`、`wsh`，可用性取决于部署环境。不能把本机路径或假定的默认 Claude 命令当作服务端配置。

`resume` 和 `replace` 默认 false。`replace: true` 会替换同名运行中的 Agent，不能自动添加。`skip_permissions` 默认 false。可用 `agent_type` 指定成员类型，默认 `general-purpose`。

启动成功仅表示服务端接受并完成了启动步骤。`agents` 的 `alive` 为 null 表示未知，不能据此认定离线。任务完成仍需核对任务状态及实际结果。服务端启动等待上限为 60 秒；需要等待完整响应时把客户端全局 `--timeout` 设为更长时间。较短的客户端超时不会取消服务端操作。

OpenAPI 每个请求都校验 Key，Key 只放在 `Authorization` 头，不接受查询参数。部署端继续负责网络访问控制。团队创建/删除、成员增删、工作区合并/清理和快照恢复尚未暴露，不能把这些命令伪装成已支持的 HTTP 操作。
