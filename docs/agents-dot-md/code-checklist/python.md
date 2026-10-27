# 代码 checklist：Python 专项

> 改 Python 代码时必须逐条对照的语言专项；通用条目见上级的 `code-checklist.md`。

---

# Python 专项

## P1. 禁止可变对象作默认参数

`def f(items=[])` / `={}` 的默认值在函数定义时求值一次，会跨调用累积，是最经典的隐蔽 bug。

- 反例：`def add(x, bucket=[]):`
- 正例：`def add(x, bucket=None): bucket = [] if bucket is None else bucket`

## P2. 不吞异常，日志用 `logger.exception` 保留堆栈

- 禁止裸 `except:`（会吞掉 `KeyboardInterrupt` / `SystemExit`）和 `except Exception: pass`。
- 捕获后要么处理、要么 `raise`；记录日志用 `logger.exception("...")` 或 `logger.error("...", exc_info=True)`，保留完整堆栈。

## P3. 日志用惰性格式化，不要 f-string

`logger.info(f"...{payload}")` 无论日志级别是否开启都会先做字符串格式化，且丢失结构化聚合能力。

- 反例：`logger.info(f"user={user_id} 处理完成")`
- 正例：`logger.info("user=%s 处理完成", user_id)`

## P4. 公共函数写类型注解

对外暴露的函数 / 方法标注参数与返回类型；返回可能为空时用 `Optional[T]` 明示，不要靠调用方猜。项目若启用 mypy / pyright，提交前跑一遍。

## P5. 文件与资源用 `with`，路径用 `pathlib`

打开文件、获取锁、连接一律走 `with`；拼路径用 `pathlib.Path` 或 `os.path.join`，不要手拼 `"/"`。文本 I/O 显式指定 `encoding="utf-8"`。

## P6. 库代码不 `print`、不在导入期做副作用

模块顶层只做定义，不发请求、不连数据库、不读配置文件（导入即执行会让测试和启动顺序变得不可控）。CLI 启动脚本可输出进度；可复用库输出使用 `logging`，并对敏感值脱敏。

## P7. 依赖与虚拟环境

新增运行依赖写入 Dockerfile，提供可复现的版本约束；测试使用镜像中的虚拟环境，不依赖宿主机恰好安装的包。
