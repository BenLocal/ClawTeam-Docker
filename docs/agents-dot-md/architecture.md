# 系统架构
> 启动入口、服务边界与 Magpie 配置导入顺序；改服务生命周期前阅读。

本仓库负责打包与部署 ClawTeam，不包含后端业务项目源码。Dockerfile 获取 ClawTeam fork、Magpie、Claude Code、dsh 与 dsh-tui 和 Docker CLI/daemon，运行时状态保存在 home 卷和 Docker 数据卷。

`docker-entrypoint.sh` 生成 Docker 客户端配置，按是否启用 DinD 选择轻量入口或 systemd。systemd 环境快照由 `systemd_runtime.py` 写入 `/run/clawteam`；Agent 环境与 dockerd 代理环境分开保存。

systemd 模式下，`docker.service` 管理内层 daemon，`magpie.service` 管理网关与 Web，`clawteam.service` 等待依赖就绪后运行 `container-entrypoint.sh`。设置 `CLAWTEAM_OPENBAO=1` 时，`openbao.service` 运行 OpenBao 密钥服务，未设置时由 `ExecCondition` 跳过。轻量模式由入口脚本监管 Magpie、Board 和 Nginx。

配置导入在 Leader 前完成：Git 凭据文件（Magpie 启动前）、原生插件、技能、MCP 依赖及服务定义、Instructions。`skills_bootstrap.Library` 提供本机鉴权 HTTP 客户端；配置写入使用 Magpie 原生 API 或 CLI。成功安装记录属于 home 卷的运行状态。

Nginx 在同一发布端口提供 `/clawteam/` 与 `/magpie/`；Board、Magpie Web 和模型网关使用各自的容器内端口。Leader 与 Worker 通过 ClawTeam 的团队存储、tmux 和 Git worktree 协作。

新增导入器时同时更新默认 YAML、镜像复制规则、启动顺序、宿主机启动脚本和适用的集成验证。改变 Magpie API 交互前核对部署版本，不直接修改其受管理的 profile 文件来绕过 API。
