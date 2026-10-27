# 运行状态核验
> 框架能力、会话状态与日志取证中已验证的边界。

- 2026-10-27：基线 ClawTeam `0119833` 的 Board “Set Context” 向 `/api/team/{team}/task` 提交资料分析任务，不保存团队级系统提示词；`TeamConfig` 只有说明与成员等元数据。模板的成员 `task` 和 `launch --goal` 是启动上下文，不能当作运行中团队持久 Instructions 的编辑接口。核对源文件 `board/static/index.html`、`team/models.py`、`spawn/prompt.py`。
- 2026-10-27：原生 `launch` 返回 `status: launched` 后，曾观察到团队已登记而对应 tmux 会话不存在；启动返回值不作为成员在线的唯一依据，必须检查注册目标和实际会话。tmux 退出根因仍待验证，不能把宿主机历史 segfault 日志直接归因于当前启动。
- 2026-10-27：Magpie 启动日志会输出带 Web Key 的登录 URL；收集 journal 时先在程序内脱敏，再输出诊断片段。
- 2026-10-27：已有 home 卷中的 `.claude.json` 曾为 root 所有、权限 `0600`，node 运行的配置导入因此失败；核对所有者后改回 node 并保留 `0600` 可恢复。更新服务前需同时核对配置内容与文件所有权；此文件变成 root 所有的来源未确认。
- 2026-10-27：部署的 Claude 新 worktree 信任界面默认选择 `No, exit`；基线 ClawTeam 的 `_startup_prompt_action()` 对目录信任返回 Enter，无法确认此界面。courselab 的部署恢复脚本按实际选项选择可信工作区，确认后检查提示消失及真实 Agent 状态。该适配只在部署脚本，尚未修改 ClawTeam fork。
