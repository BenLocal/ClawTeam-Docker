# ClawTeam Docker

ClawTeam、tmux、Git、Python、Node.js、Claude Code、Magpie、Nginx 和 Docker 工具打包在同一个容器里。宿主机仅需 Docker 和 Bash。Leader 在容器内的 tmux `clawteam:leader` 窗口运行，通过 ClawTeam 创建的 Worker 也在同一容器中运行，各自拥有 Git worktree 和 tmux 窗口。

```bash
./clawteam.sh build
# 项目必须是有至少一次提交的普通 Git 仓库（不是宿主机的 linked worktree）。
CLAWTEAM_ENV_FILE=/绝对路径/agent.env \
  ./clawteam.sh start /绝对路径/你的项目 "创建团队，实现登录功能并验证"
```

先编辑 `providers.yaml`，或用 `CLAWTEAM_PROVIDERS_FILE=/path/to/providers.yaml` 指定文件。默认配置通过环境变量 `LLM_API_BASE` 读取你的 OpenAI 兼容网关地址，因此 `agent.env` 至少需要 `LLM_API_BASE=http://your-gateway:8000/v1`。每次启动都会导入该文件并配置 Claude，凭据通过环境变量或挂载文件提供，不需要写入镜像。没有选择 Magpie 模型时，仍可使用 Claude 自身的登录配置。

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

启动脚本会添加 `--user root --privileged`，并把独立的 `<容器名>-docker` 数据卷挂到 `/var/lib/docker`。Docker daemon 以 root 运行，Leader 和 Worker 仍以 `node` 运行，通过容器内的 Unix socket 访问 daemon。停止或重建容器会保留内层镜像与数据卷。

Compose 服务启用 DinD 时增加以下配置，并保留现有的项目、home 和 providers.yaml 挂载：

```yaml
services:
  clawteam:
    user: root
    privileged: true
    environment:
      CLAWTEAM_DIND: "1"
    volumes:
      - clawteam-docker:/var/lib/docker
volumes:
  clawteam-docker:
```

运行时代理放在 Docker env-file 中，可从 [agent.env.example](agent.env.example) 复制。支持 `HTTP_PROXY`、`HTTPS_PROXY`、`NO_PROXY` 及小写形式，也支持 Agent 和内层容器使用的 `ALL_PROXY`。代理地址需要从容器内可达。启动脚本也会传入宿主环境中已设置的这些变量，优先于 env-file。

代理会应用到 Agent 和 Docker daemon；启动时还会合并 `~/.docker/config.json` 的 `proxies.default`，让内层 `docker build` 和 `docker run` 自动获得代理，同时保留已有的 registry 登录配置。`NO_PROXY` 会自动补上 `localhost`、`127.0.0.1` 和 `::1`，保证 Magpie 的本地请求直连。清空代理变量并重建容器后，会移除之前写入的默认代理。

Docker 环境变量在创建容器时确定。修改 env-file 后，用 `docker compose up -d --force-recreate` 重建服务；`docker start` 或 `docker restart` 会继续使用原来的环境变量。providers.yaml 的内容则在每次启动时重新读取。

直接用 `docker exec` 操作 DinD 容器时，用 `--user node` 进入 Agent 环境，例如 `docker exec --user node -it clawteam bash`。Docker daemon 的启动日志位于容器内 `/var/log/clawteam-dockerd.log`，由 root 读取。

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
      - ./providers.yaml:/etc/clawteam/providers.yaml:ro
      - clawteam-home:/home/node
volumes:
  clawteam-home:
```

如挂载目录包含多个项目，用 Compose 的 `working_dir: /workspace/子项目` 选择 Git 仓库，Leader 和 Worker 会使用这个仓库根目录。

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

默认镜像名为 `clawteam-local:latest`，容器名为 `clawteam`，可用 `CLAWTEAM_IMAGE`、`CLAWTEAM_CONTAINER` 覆盖。镜像默认跟随上游版本；可指定版本重建：

```bash
CLAWTEAM_REF=<tag或commit> CLAUDE_VERSION=<npm版本> \
  MAGPIE_VERSION=<镜像tag> ./clawteam.sh build
```

安装与编排方式参考 [ClawTeam 官方仓库](https://github.com/HKUDS/ClawTeam)、[Claude Code 官方仓库](https://github.com/anthropics/claude-code) 和 [Magpie 官方说明](https://github.com/yetone/magpie)。

容器集成验证：构建后运行 `python3 tests/smoke.py`。测试使用临时项目、容器和数据卷，验证同一端口的两个面板、登录、SSE、模型路由及持久化，并用模拟供应商检查 `429 → 备用模型`，不需要真实模型凭据。另运行 `python3 tests/dind_smoke.py`，使用临时 privileged 容器验证内层构建、运行、代理和 Docker 数据卷持久化。

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
