# ClawTeam-Docker agent instructions

本文件适用于本仓库及子目录，`CLAUDE.md` 链接到此。默认用简体中文交流；提交信息沿用本仓库的英文 Conventional Commits。代码注释与相邻实现保持一致。

<!-- MEM0_ACTIVE_MEMORY_START -->
## 主动记忆

会话开始时读取 `/home/shiben/.agents/mem0-policy.md`，新任务先召回。跨项目偏好与本机环境事实按该策略保存，使用 `infer=false`；本仓库的排查结论写入下述文件记忆区，同一事实只保存在一处。
<!-- MEM0_ACTIVE_MEMORY_END -->

## 项目约束

- ClawTeam 源码从 `https://github.com/BenLocal/ClawTeam.git` 获取，构建版本由 `CLAWTEAM_REF` 选择。源码修改通过镜像构建落地，运行容器中的临时补丁不能当作可交付结果。
- 五份默认 YAML 集中在 `magpie-config/`。用户指令经 `prompt.yaml` 导入 Magpie Instructions；保留未声明配置及用户手工维护的 Agent 指令。
- MCP 的 `install.command`、`install.check` 使用参数列表执行。检查实际依赖后再决定是否安装，安装成功且检查通过后才记录成功。
- 代理归一化限定在 Docker 配置和 dockerd 环境。依赖下载使用独立子进程环境，保持 Magpie、ClawTeam 和 Agent 的原始代理变量。
- systemd 模式将 Docker、Magpie、ClawTeam 分为独立服务。启动与重启改动需验证服务顺序、持久化凭据和进程恢复；非 systemd 模式仍可启动。
- 网关地址、API Key、Git 凭据来自部署环境或私有配置。入库示例使用占位值，日志和取证先脱敏。
- 团队注册、运行会话、持久提示词是不同状态。对框架能力和成员在线情况先核实现有版本，再汇报结果。

## 改动与验证

1. 先核实现状，把目标写成可检查的行为；对尚未确认的信息明确标注。
2. 保持实现简单，只修改当前任务需要的文件和边界。
3. 沿用现有模块与配置方式；新机制须有当前需求支撑。
4. 按改动运行能覆盖真实行为的检查，报告实际结果和未验证部分。

动启动流程、配置或外部依赖前读 [架构](docs/agents-dot-md/architecture.md)；写代码前读 [技术栈与验证](docs/agents-dot-md/tech-stack.md)。修改后对照 [代码清单](docs/agents-dot-md/code-checklist.md) 及对应语言专项。部署和远端检查按 [环境约定](docs/agents-dot-md/environment.md) 执行。复杂改动的证据要求见 [编码准则](docs/agents-dot-md/coding-guidelines.md)。

## 技能与记忆维护

- 项目 skill 使用 `skills/<name>/SKILL.md`；全局 skill 不复制进仓库。新增、改名或删除 skill 后运行已安装的 `agents-dot-md` 技能中的 `scripts/reindex.py .`。
- 排查结论按主题写入 `docs/memory/*.md`。首两行使用标题和 `> 摘要`，每条以绝对日期开头，写清现象、证据与结论。
- 已验证结论直接陈述；推测标注“待验证”。代码结构、提交历史和本文件已有约束不再作为记忆重复记录。
- 凭据、用户数据和完整日志不入库；摘录先脱敏。
- 增删模块或记忆文件后重新运行索引脚本，保持下方生成区域与磁盘一致。

## 📇 项目 Skill 索引（全仓 SKILL.md，脚本生成）
<!-- SKILLS:START -->
- （仓库内暂无 SKILL.md）
<!-- SKILLS:END -->

## 📂 模块文档索引（docs/agents-dot-md/，脚本生成）
<!-- MODULES:START -->
- [系统架构](docs/agents-dot-md/architecture.md) — 启动入口、服务边界与 Magpie 配置导入顺序；改服务生命周期前阅读。
- [代码检查清单](docs/agents-dot-md/code-checklist.md) — 配置、进程与凭据改动的共同检查；完成代码修改后逐项核对。
- [编码行为准则（Karpathy 防错指南 · 展开）](docs/agents-dot-md/coding-guidelines.md) — 写 / 改 / 审代码的可执行细则；AGENTS.md 顶层只留四条高压线，细则在此。
- [环境与部署](docs/agents-dot-md/environment.md) — 凭据处理、容器更新和远端状态核验的约定。
- [技术栈与验证](docs/agents-dot-md/tech-stack.md) — 本仓库的运行依赖和验证入口；构建与修改代码前阅读。
<!-- MODULES:END -->

## 🧠 记忆索引（docs/memory/，脚本生成）
<!-- MEMORY:START -->
- [运行状态核验](docs/memory/runtime.md) — 框架能力、会话状态与日志取证中已验证的边界。
<!-- MEMORY:END -->
