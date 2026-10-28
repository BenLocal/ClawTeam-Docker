# ClawTeam Docker

ClawTeam、tmux、Git、Python、Node.js、Claude Code、DeepSeek Harness（dsh 与 dsh-tui）、Magpie、Nginx 和 Docker 工具打包在同一个容器里。宿主机仅需 Docker 和 Bash。Leader 在容器内的 tmux `clawteam:leader` 窗口运行，通过 ClawTeam 创建的 Worker 也在同一容器中运行，各自拥有 Git worktree 和 tmux 窗口。

```bash
./clawteam.sh build
# 项目必须是有至少一次提交的普通 Git 仓库（不是宿主机的 linked worktree）。
CLAWTEAM_ENV_FILE=/绝对路径/agent.env \
  ./clawteam.sh start /绝对路径/你的项目 "创建团队，实现登录功能并验证"
```

先编辑 `magpie-config/providers.yaml`，或用 `CLAWTEAM_PROVIDERS_FILE=/path/to/providers.yaml` 指定文件。默认配置通过环境变量 `LLM_API_BASE` 读取你的 OpenAI 兼容网关地址，因此 `agent.env` 至少需要 `LLM_API_BASE=http://your-gateway:8000/v1`。每次启动都会导入该文件并配置 Claude，凭据通过环境变量或挂载文件提供，不需要写入镜像。没有选择 Magpie 模型时，仍可使用 Claude 自身的登录配置。

容器启动时自动注册 `clawteam-docker` 团队和 Leader，并启动任务监听器，每 5 秒检查一次变化。在 `/clawteam/` 中选择该团队，通过 New Task 新增任务后，监听器会通知 Leader 读取任务、分配 Worker 并更新状态。配置了 Magpie 模型后，会为挂载的 Git 工作目录完成首次引导和信任设置，并允许 Leader 使用 `clawteam` 命令；其他工具操作仍遵循 Claude 的权限设置，需要人工确认时通过 `./clawteam.sh attach` 操作。镜像已为 Claude 安装官方 ClawTeam skill。已有团队会复用，实际 Worker 在 Leader 分配任务时才创建。

Leader 的 Claude 进程退出后，会在 10 秒后重启，可用 `CLAWTEAM_LEADER_RESTART_DELAY` 调整间隔。供应商的凭据错误仍需修正；tmux 会保留错误信息，不能仅凭会话存在判断模型可用。

按 **Ctrl-b 再按 d** 脱离 tmux，任务继续运行。

```bash
./clawteam.sh attach   # 回到 Leader；Ctrl-b w 选择其他窗口
./clawteam.sh shell    # 进入容器，可使用 clawteam board / claude / git
./clawteam.sh web      # 显示 ClawTeam 与 Magpie 的完整访问链接
./clawteam.sh magpie   # Magpie 终端界面
./clawteam.sh stop     # 停止所有 Agent 并删除容器，保留项目和 home 卷
```

## 一个端口访问两个面板

Nginx 使用同一地址、同一端口下的两个路径，无需额外域名或 hosts 配置：

| 路径 | 界面 | 容器内部地址 |
| --- | --- | --- |
| `/clawteam/` | ClawTeam 面板 | `127.0.0.1:8081` |
| `/magpie/` | Magpie 管理界面 | `127.0.0.1:3430` |

`/clawteam` 和 `/magpie` 会自动跳转到带尾斜线的路径，根路径跳转到 `/clawteam/`。使用 `./clawteam.sh web` 获取完整地址和带登录密钥的 Magpie 链接。密钥保存在 home 卷，重启保持不变。Nginx 关闭访问日志，避免记录链接密钥。

默认绑定本机 `127.0.0.1:8080`。使用服务器 IP 访问时，指定监听地址和对外 URL：

```bash
CLAWTEAM_WEB_BIND=0.0.0.0 CLAWTEAM_WEB_PORT=18080 \
  CLAWTEAM_WEB_URL=http://192.168.1.10:18080 \
  ./clawteam.sh start /项目目录
./clawteam.sh web
# http://192.168.1.10:18080/clawteam/
# http://192.168.1.10:18080/magpie/?k=登录密钥
```

`CLAWTEAM_WEB_URL` 不带末尾斜线。也可以将 `CLAWTEAM_WEB_BIND` 设为宿主机的具体 IP。只发布 Nginx 端口，Magpie 的 `3425` 模型网关仅供容器内 Agent 使用。

上游页面目前使用根路径 API。本镜像通过 `subpath.js` 为页面的 fetch、EventSource、WebSocket 和动态图片/iframe 请求加上各自前缀，并由 Nginx 处理登录重定向、Cookie 路径和登录表单路径。静态资源保持在各自子路径下。上游升级后应运行集成测试并检查页面兼容性。Web 服务退出会使容器退出并停止 Agent。

## Docker in Docker 和启动代理

镜像包含 Docker CLI、daemon、Buildx 和 Compose。需要让 Agent 构建镜像或运行容器时启用 DinD：

```bash
CLAWTEAM_DIND=1 CLAWTEAM_ENV_FILE=/path/to/agent.env \
  ./clawteam.sh start /项目目录
./clawteam.sh shell
# 容器内可以执行 docker build、docker run、docker compose。
```

启动脚本会添加 `--user root --privileged --init=false`，并把独立的 `<容器名>-docker` 数据卷挂到 `/var/lib/docker`。DinD 模式下 systemd 作为 PID 1：`docker.service` 以 root 运行和守护 dockerd，`clawteam.service` 以 `node` 启动 Leader、Worker 和面板，通过容器内的 Unix socket 访问 Docker。停止或重建容器会保留内层镜像与数据卷。

Compose 服务启用 DinD 时增加以下配置，并保留现有的项目、home 和 providers.yaml 挂载：

```yaml
services:
  clawteam:
    user: root
    privileged: true
    init: false
    cgroup: private
    stop_signal: SIGRTMIN+3
    stop_grace_period: 60s
    tmpfs:
      - /run
      - /tmp:mode=1777
    environment:
      CLAWTEAM_DIND: "1"
    volumes:
      - clawteam-docker:/var/lib/docker
volumes:
  clawteam-docker:
```

运行时代理放在 Docker env-file 中，可从 [agent.env.example](agent.env.example) 复制。支持 `HTTP_PROXY`、`HTTPS_PROXY`、`NO_PROXY` 及小写形式，也支持 Agent 和内层容器使用的 `ALL_PROXY`。代理地址需要从容器内可达。启动脚本也会传入宿主环境中已设置的这些变量，优先于 env-file。

同一个 `agent.env` 也可添加部署者自己的环境变量，按 Docker env-file 的 `KEY=value` 格式填写，不需要修改镜像。Compose 使用 `env_file: ./agent.env`，启动脚本使用 `CLAWTEAM_ENV_FILE=/path/to/agent.env`。变量会进入容器环境、Leader、Worker 和 `docker exec` 打开的 shell；DinD 模式的 `clawteam.service` 同样会接收自定义变量，`HOME`、`USER`、`LOGNAME` 保留 node 用户设置。具体变量和值由部署者决定。除代理外，内层 Docker 容器和构建所需的自定义变量仍使用 `docker run --env` 或构建参数显式传入。

Docker 代理归一化仅写入 dockerd 的 systemd 环境和 `~/.docker/config.json` 的 `proxies.default`，让内层 `docker build` 和 `docker run` 获得代理，并保留 registry 登录。Docker 的 `NO_PROXY` 补上本机地址；Agent 和 Magpie 的原始代理变量保持不变。清空代理变量并重建容器后会移除之前写入的默认代理。

Docker 环境变量在创建容器时确定。修改 env-file 后，用 `docker compose up -d --force-recreate` 重建服务；`docker start` 或 `docker restart` 会继续使用原来的环境变量。providers.yaml 的内容则在每次启动时重新读取。

直接用 `docker exec` 操作 DinD 容器时，用 `--user node` 进入 Agent 环境，例如 `docker exec --user node -it clawteam bash`。服务状态、重启和日志通过 systemd 管理：

```bash
docker exec --user root clawteam systemctl status docker
docker exec --user root clawteam systemctl restart docker
docker exec --user root clawteam journalctl -u docker --no-pager -n 100
docker exec --user root clawteam systemctl status clawteam
```

Docker daemon 异常退出后由 systemd 重启；重启 Docker 服务会暂时中断内层 Docker 操作，ClawTeam 服务保持运行。应用进程退出时，systemd 会正常关闭容器并把应用退出状态返回给 Docker。未启用 DinD 的启动方式仍使用轻量入口，不启动 systemd。

## Magpie 独立服务

启用 systemd 时，`magpie.service` 独立管理 Magpie 网关和 Web，异常退出后自动重启。ClawTeam 在 Magpie 就绪后导入配置并启动 Agent；Magpie 运行时重启不会主动结束 Leader，持久化 Web Key 保持不变。

```bash
docker exec --user root clawteam systemctl status magpie
docker exec --user root clawteam systemctl restart magpie
```

查看 Magpie journal 时先脱敏带 Key 的登录链接。未启用 systemd 时，仍由轻量入口监管 Magpie。

## Claude Code 自动切换模型

容器默认命令为 `start`，使用 `docker run` 不指定命令时也会自动启动服务和 Leader。`docker start`、`docker restart` 及 Compose 重建容器都会在启动时重新读取 `/etc/clawteam/providers.yaml`，按 ID 更新 provider 和路由组，不会生成重复的 provider。文件未列出的既有配置会保留。

下面是 OpenCode Go 的配置示例；其他 OpenAI 兼容网关使用 `api: openai`，`url` 设为该网关的 `/v1` 地址。可以用 `url_env` 从环境变量读取地址。

```yaml
providers:
  - id: opencode-go
    api: anthropic
    url: https://opencode.ai/zen/go
    key_env: OPENCODE_GO_API_KEY
    key_required: true
    models:
      - deepseek-v4.1-flash

groups: []

claude:
  model: opencode-go/deepseek-v4.1-flash
```

在 Docker env-file 中设置 `OPENCODE_GO_API_KEY=你的Key`。也可在只读挂载的 YAML 中使用 `key: "你的Key"`；将包含凭据的文件放在仓库外，并确保容器用户 UID 1000 可读。`key` 与 `key_env` 只能选一个；`url` 与 `url_env` 同样只能选一个。`key_env` 和 `url_env` 引用的变量必须在容器中存在，免认证供应商使用 `key: ""`。需要凭据的供应商设置 `key_required: true`；Key 为空时面板仍可使用，Leader 会话等待配置，不发起模型请求。填写 YAML 中的 Key 后重启容器即可生效。

使用 Compose 时挂载配置，并保留 home 数据卷：

```yaml
services:
  clawteam:
    image: clawteam-local:latest
    init: true
    restart: unless-stopped
    env_file: agent.env
    volumes:
      - /你的Git项目:/workspace
      - ./magpie-config:/etc/clawteam:ro
      - clawteam-home:/home/node
volumes:
  clawteam-home:
```

如挂载目录包含多个项目，用 Compose 的 `working_dir: /workspace/子项目` 选择 Git 仓库，Leader 和 Worker 会使用这个仓库根目录。

## 启动时导入技能

编辑 `magpie-config/skills.yaml`，填写容器内的本地目录或 Magpie 支持的 Git 仓库地址：

```yaml
sources:
  - source: /workspace/aiclass-skills/skills
    agents: [claude]
  - source: https://github.com/your-org/other-skills.git
    agents: [claude]
```

`./clawteam.sh start` 默认挂载仓库中的 `magpie-config/skills.yaml`，也可用 `CLAWTEAM_SKILLS_FILE=/path/to/skills.yaml` 选择宿主机文件。Compose 按上例挂载。直接运行 Docker 时，可挂载到 `/etc/clawteam/skills.yaml`，或通过容器环境变量 `CLAWTEAM_SKILLS_FILE` 指定其他容器内路径。默认 `sources: []` 不导入技能。

每次启动都会在 Magpie 就绪后扫描来源，通过 Library 安装新技能并同步，然后启动 Leader。已有同名技能会跳过并记录日志，保留其内容、来源和 Agent 分配；删除来源条目不会卸载技能。后续修改已有技能的分配或更新远端内容，请在 Magpie 的 Library 页面操作。本地目录使用链接，文件改动直接可见；远端技能不会在启动时自动覆盖更新。私有仓库使用容器用户自己的 Git 凭据，访问权限需预先配置。

配置、扫描、安装或同步失败时，启动会退出，Leader 不会运行；通过 `docker logs` 查看错误。导入使用持久化的 Magpie Web Key 认证，不需要在 `magpie-config/skills.yaml` 填 Key。自带的 ClawTeam 技能继续由镜像提供。

启用 DinD/systemd 时，`clawteam-skills-update.timer` 会在启动约 5 分钟后、随后每小时触发一次更新，另有最多 1 分钟的随机延迟。更新服务只处理 `magpie-config/skills.yaml` 中的 Git 来源，补入新技能并通过 Library 更新已安装的同源技能，随后同步给 Agent。手工安装或其他来源的同名技能不参与更新；本地修改冲突和仓库中已删除的技能会保留并报告失败，下次定时执行会再次尝试。已有 Claude 会话可能缓存技能内容，更新后新建会话使用新内容。

```bash
docker exec --user root clawteam systemctl list-timers clawteam-skills-update.timer
docker exec --user root clawteam systemctl start clawteam-skills-update.service
docker exec --user root clawteam journalctl -u clawteam-skills-update.service --no-pager -n 50
```

调整周期时，在 `/etc/systemd/system/clawteam-skills-update.timer.d/override.conf` 中设置 `[Timer]` 下的 `OnUnitActiveSec=30min`，再执行 `systemctl daemon-reload` 和 `systemctl restart clawteam-skills-update.timer`。需要跨容器重建保留时挂载该目录。未启用 systemd 时，可手动运行 `docker exec --user node clawteam python3 /usr/local/lib/clawteam-docker/skills_bootstrap.py --update`。更新服务沿用容器的 Git 认证和代理环境；失败只影响本次更新，不重启 Leader。

## Magpie 配置目录

`magpie-config/` 集中存放 `providers.yaml`、`skills.yaml`、`prompt.yaml`、`mcp.yaml` 和 `plugin.yaml`。使用 Compose 时将这个目录只读挂载到 `/etc/clawteam`；`agent.env` 留在外层。镜像默认包含 Node.js 22 和 npm，MCP 依赖可以在启动时按 YAML 安装。

## 导入 Instructions

编辑 `magpie-config/prompt.yaml`，通过 Magpie Instructions 管理用户指令：

```yaml
instructions:
  shared: |
    请使用中文汇报进度。
  agents: [claude]
  extra:
    claude: |
      完成任务后说明改动和验证结果。
```

`shared` 是当前启用指令集的共享内容，`agents` 指定接收指令的 Agent，`extra` 是各 Agent 的附加内容。只更新文件中明确配置的字段，未配置字段保留；`shared: ""` 或 `extra: {claude: ""}` 清空对应文本，`agents: []` 停用分发。默认 `instructions: {}` 保留现有配置，不发起导入。

`./clawteam.sh start` 默认挂载仓库中的 `magpie-config/prompt.yaml`，可用 `CLAWTEAM_PROMPT_FILE=/path/to/prompt.yaml` 选择宿主机文件。Docker/Compose 将文件只读挂载到 `/etc/clawteam/prompt.yaml`；需要其他容器内路径时设置 `CLAWTEAM_PROMPT_FILE`。每次启动都会在 Magpie 就绪后、Leader 启动前导入。修改后重启容器即可生效，重复导入不会叠加文本。

Magpie 会把指令写入 Agent 的用户级指令文件，例如 Claude 的 `~/.claude/CLAUDE.md`，Leader 和新启动的 Worker 都可读取；Magpie 管理区外的手工内容会保留。YAML 中配置的字段会在每次启动时覆盖对应 Library 值。配置或同步失败时不启动 Leader。ClawTeam 运行所需的团队身份与任务调度指令仍由入口提供。

## 预装 MCP 和插件

`magpie-config/mcp.yaml` 使用完整的 MCP 服务定义，按名称创建或更新，未列出的服务会保留：

```yaml
servers:
  - name: local-tools
    transport: stdio
    command: python3
    args: [/workspace/mcp/server.py]
    env:
      MODE: "production"
    agents: [claude]
  - name: remote-tools
    transport: http
    url: https://mcp.example.com/mcp
    headers: {}
    agents: [claude]
```

`transport` 支持 `stdio`、`http` 和 `sse`。命令参数、环境变量和请求头中的值必须是字符串。服务通过 Library 同步到 Agent；配置导入不代表服务端已连通，远端认证和 YAML 未声明的运行依赖需要部署者准备。默认 `servers: []` 不改动现有 MCP 配置。包含凭据的 YAML 应放在仓库外，限制宿主机权限并允许 UID 1000 读取。

每个 MCP 服务可以用 `install` 声明安装命令和检查命令，均为参数列表。例如：

```yaml
servers:
  - name: codegraph
    transport: stdio
    install:
      command: [npm, install, --global, --prefix, /home/node/.local, "@colbymchenry/codegraph@1.6.2", --prefer-offline, --no-audit, --no-fund]
      check: [/home/node/.local/bin/codegraph, --version]
    command: /home/node/.local/bin/codegraph
    args: [serve, --mcp]
    agents: [claude]
```

安装以容器用户 `node` 执行，直接运行参数列表，不通过 Shell 解释。建议使用持久化 home 卷下的 `/home/node/.local` 安装目录。每次启动先执行 `check`；同一安装配置已成功执行且检查通过时跳过安装。安装命令变化或依赖缺失时重新安装，安装完成后再次检查，失败则不启动 Leader。安装命令最多等待 10 分钟，检查命令最多等待 1 分钟；成功记录保存在 home 卷，`install` 不会写入 Agent 的 MCP 定义。

`magpie-config/plugin.yaml` 使用插件来源列表，语法与 `magpie plugin add` 一致：

```yaml
plugins:
  - "@your-org/magpie-plugin@1.0.0"
  - /workspace/my-plugin.js
```

支持 Magpie 原生的社区名称、npm 包、Git 来源和容器内路径。已有插件保留启用状态与选项，不重复添加；修改来源或版本后在下次启动安装。删除列表条目不会卸载插件。安装依赖和插件登录沿用 Magpie 原生行为，插件运行使用镜像预装的 Bun；需要账号的插件仍需完成登录。某个插件安装失败时，启动日志记录警告并跳过该条目，Leader 照常启动，下次启动重试；格式不合法的 `plugin.yaml` 仍会中止启动。默认 `plugins: []` 不安装插件。

`tools` 类插件（例如社区插件 `LayerFS`）的工具由 Magpie 网关的 `/mcp/magpie/tools` 提供，名为 `<插件>_<工具>`。在 `mcp.yaml` 中声明后同步给 Agent：

```yaml
servers:
  - name: magpie-tools
    transport: http
    url: http://127.0.0.1:3425/mcp/magpie/tools
    agents: [claude, codex]
```

网关只监听容器内 `127.0.0.1:3425`，Nginx 不转发该路径。插件工具以容器用户 `node` 的权限运行，启用会执行命令的工具前先确认其选项。

启动脚本默认挂载这两个文件，也可通过宿主机环境变量 `CLAWTEAM_MCP_FILE`、`CLAWTEAM_PLUGIN_FILE` 指定文件。Docker/Compose 分别挂载到 `/etc/clawteam/mcp.yaml`、`/etc/clawteam/plugin.yaml`。这些配置在 Magpie 就绪后、Leader 启动前导入，修改后重启容器生效。

`MIRROR_HTTP_PROXY` 优先用于 Docker 的代理配置，以及 MCP/插件安装子进程的下载环境。归一化后的变量不会导出到整个容器，也不会改写 Magpie、ClawTeam 或 Agent 的原始代理变量。安装结束后调用方环境保持不变；原始 `HTTP_PROXY`、`HTTPS_PROXY`、`NO_PROXY` 仍由部署者控制。内部配置 API 及本机就绪检查直接访问本机。

多个模型可通过 YAML 创建路由组：

```yaml
groups:
  - id: coding
    models: [provider-a/model-a, provider-b/model-b]
    routing: order
    stays: "off"
claude:
  model: group/coding
```

`stays: "off"` 需要引号，避免 YAML 将 `off` 解析为布尔值。环境变量 `CLAWTEAM_MODEL` 优先于 YAML 的 `claude.model`；两者都留空时沿用 home 卷里已保存的 Magpie 模型。可以继续在 Magpie 页面或 CLI 中管理未列入启动文件的配置。以下 `provider-a/model-a` 等均为占位符，请换成 `magpie models` 列出的真实 ID：

```bash
./clawteam.sh magpie providers
./clawteam.sh magpie models
./clawteam.sh magpie group add coding \
  models=provider-a/model-a,provider-b/model-b routing=order
./clawteam.sh magpie claude group/coding
```

`order` 在当前成员无法响应时尝试下一成员；`rotate` 按轮次轮换，`smart` 根据可用订阅额度选择。仅安装 Magpie 不会自动产生候选模型，必须先配置供应商和路由组。Magpie 负责协议适配，Claude Code 通过本容器网关调用组内模型。

修改 Claude Code 的模型设置后开启新会话。也可停止容器后指定路由组重新启动 Leader，Worker 会共用该配置：

```bash
./clawteam.sh stop
CLAWTEAM_MODEL=group/coding ./clawteam.sh start /项目目录 "继续任务"
```

启动时选定 Magpie 模型后，会从 Leader/其 Worker 环境中去掉直连 Anthropic 的变量，以使用 Magpie 写入的设置。首次配置前不要指定不存在的组。`docker exec` 新开的 shell 仍会继承容器创建时的环境；如在那里手动运行 Claude，请先取消直连变量。Magpie 的供应商、路由组、登录状态及用量记录同样保存在 home 卷。

项目挂载到 `/workspace`，修改会直接写回宿主机；Linux 上项目需允许容器用户 UID 1000 读写。`<容器名>-home` Docker 卷保存 Claude 登录状态、ClawTeam 消息及配置；停止后重启可保留这些文件，但不会恢复已结束的 Agent 进程或 tmux 会话。Git worktree 元数据使用容器路径，运行期间请在容器里管理 Worker worktree。不要传入宿主机 linked worktree，其 `.git` 路径在容器内可能无效。

默认镜像名为 `clawteam-local:latest`，容器名为 `clawteam`，可用 `CLAWTEAM_IMAGE`、`CLAWTEAM_CONTAINER` 覆盖。ClawTeam 源码默认使用 [BenLocal/ClawTeam 的 self 分支](https://github.com/BenLocal/ClawTeam/tree/self)；可通过 `CLAWTEAM_REF` 指定该 fork 中的其他分支、tag 或 commit 重建：

```bash
CLAWTEAM_REF=<tag或commit> CLAUDE_VERSION=<npm版本> CODEX_VERSION=<npm版本> BUN_VERSION=<版本> \
  DSH_VERSION=<npm版本> DSH_TUI_VERSION=<npm版本> MAGPIE_VERSION=<镜像tag> ./clawteam.sh build
```

镜像设置 `DISABLE_AUTOUPDATER=1`，关闭 Claude Code 在容器内的自动更新；工具版本随镜像构建固定，升级时重新构建镜像。

镜像预装 Bun（`BUN_VERSION`，默认 1.4.2，按发布包的 SHA256 校验），并设置 `MAGPIE_BUN=/usr/local/bin/bun`，Magpie 运行插件时不再从 GitHub 下载 Bun。

镜像预装 DeepSeek Harness（`DSH_VERSION`，默认 0.2.1-rc.2）和 dsh-tui 插件（`DSH_TUI_VERSION`，默认 0.17.0）。dsh-tui 只接受它声明的 dsh 版本，两者要一起升级。TUI profile 在构建时生成于 `/opt/dsh/profiles/tui`，首次启动时复制到 home 卷的 `~/.dsh/profiles/tui`；之后的插件变更和 Magpie 写入的模型配置都留在卷里。已有的 profile 不会随镜像升级替换，需要换成新镜像的版本时，删除该目录再重启容器。启动时选定 Magpie 模型后，dsh 的所有 profile 使用同一个模型。Worker 可用 `clawteam spawn tmux dsh tui --team ...` 创建，需要 `CLAWTEAM_REF` 指向包含 dsh 适配的 ClawTeam 版本。

安装与编排方式参考 [ClawTeam 官方仓库](https://github.com/HKUDS/ClawTeam)、[Claude Code 官方仓库](https://github.com/anthropics/claude-code) 和 [Magpie 官方说明](https://github.com/yetone/magpie)。

容器集成验证：构建后运行 `python3 tests/smoke.py`。测试使用临时项目、容器和数据卷，验证同一端口的两个面板、登录、SSE、模型路由及持久化，并用模拟供应商检查 `429 → 备用模型`，不需要真实模型凭据。另运行 `python3 tests/dind_smoke.py`，使用临时 privileged 容器验证内层构建、运行、代理和 Docker 数据卷持久化。

## Vikunja 评论接单

可选的 [Vikunja 桥接](integrations/vikunja/README.md) 按 YAML 中的项目映射，将新评论 `/clawteam run` 对应的任务交给团队 Leader。桥接包含签名校验、持久队列和重复投递去重，独立部署在宿主机。需要用户决定时，可将 [决策沟通规则](integrations/vikunja/decision-policy.md) 加入团队提示词。

## GitHub CI 与镜像发布

工作流位于 `.github/workflows/docker-release.yml`，镜像发布到 `ghcr.io/benlocal/clawteam-docker`，名称自动转换为小写。使用 GitHub 自带的 `GITHUB_TOKEN`，无需额外配置 Docker Hub 或个人令牌。

| 触发方式 | 行为与镜像标签 |
| --- | --- |
| Pull Request | 构建 amd64 镜像并运行集成测试，不发布 |
| 推送到 `main` / `master` | 测试后发布分支标签、`sha-<短SHA>`；默认分支还发布 `edge` |
| 推送 `v1.2.3` 等版本标签 | 测试后发布 `1.2.3`、`1.2`、`latest` 和 SHA 标签 |
| Actions → Docker CI and Release → Run workflow | 对选定分支或标签手动执行测试和发布 |

发布镜像包含 `linux/amd64` 和 `linux/arm64`。集成测试在 amd64 上运行，arm64 通过 QEMU 构建。预发布版本（例如 `v1.2.3-rc.1`）生成预发布版本标签，不覆盖 `latest`。构建缓存保存在 GitHub Actions Cache。

将项目上传 GitHub 并启用 Actions 后，可推送版本标签触发发布：

```bash
git tag v1.0.0
git push origin v1.0.0
```

首次发布后，若需要匿名拉取，在 GitHub 的 Packages 设置里将镜像包可见性改为 Public；组织仓库还需允许工作流写入 Packages。使用已发布镜像时先拉取，再交给启动脚本：

```bash
docker pull ghcr.io/benlocal/clawteam-docker:1.0.0
CLAWTEAM_IMAGE=ghcr.io/benlocal/clawteam-docker:1.0.0 \
  ./clawteam.sh start /项目目录
```

工作流参考 [Docker 官方多架构构建说明](https://docs.docker.com/build/ci/github-actions/multi-platform/) 和 [GitHub 官方镜像发布说明](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)。

## 远程 HTTP skill

[skills/clawteam](skills/clawteam/SKILL.md) 是纯 HTTP 客户端，全部操作经 `/clawteam/openapi/` 调用：派发和更新任务、发送消息、启动 Agent、查询快照及监听进度。它不依赖 ah 或 SSH。服务端在 `agent.env` 设置 `CLAWTEAM_BOARD_API_KEY` 后才开放该接口，客户端用同一 Key 作 Bearer 认证。修改 env-file 后需重建容器。
