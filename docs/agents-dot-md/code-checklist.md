# 代码检查清单
> 配置、进程与凭据改动的共同检查；完成代码修改后逐项核对。

## 配置边界

- 规则：先校验完整输入，再执行安装或 API 写入。
- 反例：配置后半段有非法字段，前半段已执行依赖安装。
- 正例：`read_servers()` 完成校验后进入 `configure()`。
- 强制：配置导入单元测试与容器集成测试。

## 凭据与环境

- 规则：示例使用占位值；安装命令的环境从副本构造，保护调用方环境。
- 反例：把 MIRROR 代理导出为所有服务的 HTTP 代理，或在错误信息中回显完整命令及凭据。
- 正例：Docker 配置用 `docker_environment()`，安装子进程用 `download_environment()`，日志只输出阶段和脱敏诊断。
- 强制：代理环境回归测试及提交 diff 自检。

## 生命周期与持久化

- 规则：服务拆分需验证依赖就绪、异常恢复、退出状态及卷数据保留。
- 反例：只检查 unit 为 active 就认为 Leader 在线。
- 正例：同时验证 unit、真实 API、会话与实际进程。
- 强制：`tests/smoke.py`、`tests/dind_smoke.py` 对应场景。

## 幂等与已有数据

- 规则：重跑操作时保留未列出的用户配置，成功记录只能在检查通过后写入。
- 反例：依赖下载失败后仅凭插件条目存在就跳过安装。
- 正例：检查运行依赖和安装指纹，失败后保留重试路径。
- 强制：MCP、插件和 Instructions 的重启集成验证。

## 语言专项

改到哪种语言，就同时核对对应文件。

<!-- CHECKLIST:START -->
- [代码 checklist：JavaScript 专项](code-checklist/javascript.md) — 改 JavaScript 代码时必须逐条对照的语言专项；通用条目见上级的 `code-checklist.md`。
- [代码 checklist：Python 专项](code-checklist/python.md) — 改 Python 代码时必须逐条对照的语言专项；通用条目见上级的 `code-checklist.md`。
<!-- CHECKLIST:END -->
