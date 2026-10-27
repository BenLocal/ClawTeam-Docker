# 运行状态核验
> 框架能力、会话状态与日志取证中已验证的边界。

- 2026-10-27：基线 ClawTeam `0119833` 的 Board “Set Context” 向 `/api/team/{team}/task` 提交资料分析任务，不保存团队级系统提示词；`TeamConfig` 只有说明与成员等元数据。模板的成员 `task` 和 `launch --goal` 是启动上下文，不能当作运行中团队持久 Instructions 的编辑接口。核对源文件 `board/static/index.html`、`team/models.py`、`spawn/prompt.py`。
- 2026-10-27：原生 `launch` 返回 `status: launched` 后，曾观察到团队已登记而对应 tmux 会话不存在；启动返回值不作为成员在线的唯一依据，必须检查注册目标和实际会话。tmux 退出根因仍待验证，不能把宿主机历史 segfault 日志直接归因于当前启动。
- 2026-10-27：Magpie 启动日志会输出带 Web Key 的登录 URL；收集 journal 时先在程序内脱敏，再输出诊断片段。
- 2026-10-27：已有 home 卷中的 `.claude.json` 曾为 root 所有、权限 `0600`，node 运行的配置导入因此失败；核对所有者后改回 node 并保留 `0600` 可恢复。更新服务前需同时核对配置内容与文件所有权；此文件变成 root 所有的来源未确认。
- 2026-10-27：部署的 Claude 新 worktree 信任界面默认选择 `No, exit`；基线 ClawTeam 的 `_startup_prompt_action()` 对目录信任返回 Enter，无法确认此界面。courselab 的部署恢复脚本按实际选项选择可信工作区，确认后检查提示消失及真实 Agent 状态。该适配只在部署脚本，尚未修改 ClawTeam fork。
- 2026-10-27：Actions `40518351434`（`e7cbba5`）和 `40517389413` 均在 `tests/smoke.py` 首次启动时因 Magpie Git 技能扫描 HTTP 400 失败，镜像构建通过。用 CI 相同 Magpie `v0.1.1734` 的隔离复现确认：`file://` 来源仓库属主 UID 1001、Magpie 用户 UID 1000 时，Git 的 `upload-pack` 报 `detected dubious ownership`，实际校验路径为来源仓库的 `.git`。`tests/smoke.py` 通过 `GIT_CONFIG_COUNT` 注入的信任会在 Git 启动本地传输子进程时被清除；仅改工作树权限或补同类环境变量不能解决。相同属主时 API 为 200；在隔离容器内为该 `.git` 精确配置用户全局 `safe.directory` 后，克隆及 API 恢复 200。smoke 测试现为临时 home 卷预置该 `.git` 的精确信任，仅作用于被测容器和测试夹具。
