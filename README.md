# ClawTeam Docker

ClawTeam、tmux、Git、Python、Node.js、Claude Code、Magpie 和 Nginx 打包在同一个容器里。宿主机仅需 Docker 和 Bash。Leader 在容器内的 tmux `clawteam:leader` 窗口运行，通过 ClawTeam 创建的 Worker 也在同一容器中运行，各自拥有 Git worktree 和 tmux 窗口。

```bash
./clawteam.sh build
# 项目必须是有至少一次提交的普通 Git 仓库（不是宿主机的 linked worktree）。
./clawteam.sh start /绝对路径/你的项目 "创建团队，实现登录功能并验证"
```

首次启动在 Claude Code 界面完成登录和项目授权；也可以启动前设置 `ANTHROPIC_API_KEY`。脚本自动传入已设置的 `ANTHROPIC_API_KEY`、`ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_BASE_URL`。额外配置可通过 `CLAWTEAM_ENV_FILE=/path/to/agent.env` 传入，文件采用 Docker env-file 格式。凭据不会写入镜像。

Leader 启动时会收到使用 ClawTeam 建队、拆分和协调 Worker 的系统提示；实际 Worker 在 Leader 分配任务时才创建。镜像已为 Claude 安装官方 ClawTeam skill。

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

## Claude Code 自动切换模型

首次启动后打开 Magpie，添加供应商及凭据，再在 Agents 页面为 Claude Code 选择模型或路由组。也可以用 CLI 配置。以下 `provider-a/model-a` 等均为占位符，请换成 `magpie models` 列出的真实 ID：

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

`CLAWTEAM_MODEL` 会在 Leader 启动前调用 `magpie claude`，并从 Leader/其 Worker 环境中去掉直连 Anthropic 的变量，以使用 Magpie 写入的设置。首次配置前不要指定不存在的组。留空时沿用原配置，宿主机传入的 `ANTHROPIC_*` 变量可能覆盖 Magpie 配置。`docker exec` 新开的 shell 仍会继承容器创建时的环境；如在那里手动运行 Claude，请先取消直连变量。Magpie 的供应商、路由组、登录状态及用量记录同样保存在 home 卷。

项目挂载到 `/workspace`，修改会直接写回宿主机；Linux 上项目需允许容器用户 UID 1000 读写。`<容器名>-home` Docker 卷保存 Claude 登录状态、ClawTeam 消息及配置；停止后重启可保留这些文件，但不会恢复已结束的 Agent 进程或 tmux 会话。Git worktree 元数据使用容器路径，运行期间请在容器里管理 Worker worktree。不要传入宿主机 linked worktree，其 `.git` 路径在容器内可能无效。

默认镜像名为 `clawteam-local:latest`，容器名为 `clawteam`，可用 `CLAWTEAM_IMAGE`、`CLAWTEAM_CONTAINER` 覆盖。镜像默认跟随上游版本；可指定版本重建：

```bash
CLAWTEAM_REF=<tag或commit> CLAUDE_VERSION=<npm版本> \
  MAGPIE_VERSION=<镜像tag> ./clawteam.sh build
```

安装与编排方式参考 [ClawTeam 官方仓库](https://github.com/HKUDS/ClawTeam)、[Claude Code 官方仓库](https://github.com/anthropics/claude-code) 和 [Magpie 官方说明](https://github.com/yetone/magpie)。

容器集成验证：构建后运行 `python3 tests/smoke.py`。测试使用临时项目、容器和数据卷，验证同一端口的两个面板、登录、SSE、模型路由及持久化，并用模拟供应商检查 `429 → 备用模型`，不需要真实模型凭据。

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
