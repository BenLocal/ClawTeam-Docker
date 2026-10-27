# Vikunja → ClawTeam

桥接独立运行在 Docker 宿主机，接收 Vikunja 签名事件，通过 `docker exec` 在 ClawTeam 容器创建任务。
需要 Python 3.10+、Docker CLI 和 `requirements.txt` 中的依赖。宿主机服务为 `clawteam-vikunja-bridge.service`，配置默认位于 `/etc/clawteam-vikunja/config.yaml`。

## 安装

以下命令在宿主机以管理员身份执行，仓库工作目录为当前目录：

```bash
install -d /opt/clawteam-vikunja /etc/clawteam-vikunja /var/lib/clawteam-vikunja
cp integrations/vikunja/bridge.py integrations/vikunja/requirements.txt /opt/clawteam-vikunja/
python3 -m venv /opt/clawteam-vikunja/.venv
/opt/clawteam-vikunja/.venv/bin/pip install -r /opt/clawteam-vikunja/requirements.txt
cp integrations/vikunja/config.example.yaml /etc/clawteam-vikunja/config.yaml
(umask 077; python3 -c 'import secrets; print(secrets.token_hex(32))' > /etc/clawteam-vikunja/webhook.secret)
docker exec -u node clawteam mkdir -p /home/node/.local/lib/vikunja-bridge
docker cp integrations/vikunja/dispatch.py clawteam:/home/node/.local/lib/vikunja-bridge/dispatch.py
docker exec clawteam chmod 644 /home/node/.local/lib/vikunja-bridge/dispatch.py
cp integrations/vikunja/clawteam-vikunja-bridge.service /etc/systemd/system/
```

仅首次安装生成密钥；更新时保留已有密钥、配置和队列。按部署环境修改 YAML 中的 Vikunja URL、监听地址、容器名和项目映射，再启动：

```bash
systemctl daemon-reload
systemctl enable --now clawteam-vikunja-bridge
```

默认监听 `127.0.0.1:28089`，由宿主机反向代理转发。如使用 ClawTeam 容器内 Nginx，需将监听地址改为容器可访问的宿主机 IP，并在 Nginx 的 `server` 中添加精确路由（`bridge-host.example.com` 替换为该宿主机地址）：

```nginx
location = /hooks/vikunja {
    client_max_body_size 1m;
    proxy_connect_timeout 5s;
    proxy_read_timeout 15s;
    proxy_pass http://bridge-host.example.com:28089/hooks/vikunja;
}
```

校验 Nginx 配置后热加载，并将配置文件持久挂载到容器。Vikunja 的目标 URL 使用与 ClawTeam 相同的对外端口和 `/hooks/vikunja` 路径。

`projects` 以 Vikunja 项目 ID 为键，示例（123 为占位 ID）：

```yaml
trigger:
  command: /clawteam run
projects:
  123:
    team: courselab
    leader: leader
    enabled: true
    label: clawteam  # 可选
  456:
    team: clawteam-docker
    leader: leader
    enabled: true
```

只有新评论的完整正文为 `/clawteam run` 才触发；命令可在 `trigger.command` 修改。
兼容 Vikunja 富文本段落与空格。普通评论、引用、代码块、带额外正文的评论和编辑旧评论均不触发。
省略 `label` 表示该项目未完成任务均可用命令触发；保留则还要求任务带该标签。
初始为空映射，必须先配置项目，并在 Vikunja 对应项目设置 webhook。
配置的团队须已存在，Leader 须正确，团队任务监听器须运行。

## 启用一个项目

1. 编辑配置的 `projects`，使用真实项目 ID。配置每次请求和派发时重新读取，无须重启。
2. 在 Vikunja 对应项目的 Webhooks 中添加入口 URL。
3. 仅选择 `task.comment.created`。
4. Secret 填入 YAML 中 `secret_file` 指向的文件内容；不要把密钥提交到仓库。
5. 在一条无副作用的测试任务下新发评论 `/clawteam run`，核对 ClawTeam 任务和 Leader 响应，再开始投递真实工作。

仅修改路由配置不会自动注册 Vikunja webhook。若更改监听地址、队列路径或端口，需要重启服务。
新建或编辑任务不会派发；添加标签后也需新发命令评论。当前支持启动命令，不支持 stop/status/retry。

## 行为与边界

- 使用原始请求体的 HMAC-SHA256 校验 `X-Vikunja-Signature`。
- 接收后先写 SQLite，再返回 202；派发失败在本地重试。
- 按来源 URL 去重，容器内以任务 metadata 再次去重，防止派发后进程退出造成重复。同一任务重复评论命令也只创建一条任务，不作为重跑。
- 这是首次投递桥接：后续更新不会覆盖已投递任务，不同步评论、删除、完成状态，也不扫描历史任务。
- 排队后的内容是首次事件快照；后续在 Vikunja 完成或删除任务不会撤销已排队工作。需停止派发时先禁用项目路由。
- 禁用路由暂停队列任务；变更已排队任务的目标不自动迁移，需人工检查。
- 未配置项目、已完成任务、不匹配标签或命令的事件返回 200 ignored。
- Vikunja 本身可能限制内网 webhook 目标；需实际投递验证，不能只看健康检查。
- 外部事件未到达桥接端时，本地队列无法补救，需检查 Vikunja 的投递日志。

需要团队在 Vikunja 评论中向用户提问时，将 [决策沟通规则](decision-policy.md) 追加到团队 Leader 提示词，并向运行中的会话说明新规则。Leader 的 Vikunja 账号须具备来源项目的读取及评论权限；webhook 入站成功不代表机器人已有回写权限。

## 查看状态

```bash
systemctl status clawteam-vikunja-bridge
journalctl -u clawteam-vikunja-bridge -n 50 --no-pager
curl http://127.0.0.1:28089/health
```

部署在宿主机，dispatch.py 保存在容器 home 持久卷中；重建 clawteam 容器时保留该卷即可。
