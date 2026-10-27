# 代码 checklist：JavaScript 专项

> 改 JavaScript 代码时必须逐条对照的语言专项；通用条目见上级的 `code-checklist.md`。

---

# JavaScript 专项

## S1. 一律 `===`，声明用 `const` / `let`

禁止 `==`（隐式类型转换）和 `var`（函数作用域 + 提升）。默认 `const`，需要重新赋值才用 `let`。

## S2. 不允许游离的 Promise

异步调用必须 `await`、`return`，或显式 `.catch(...)`。漏掉会变成 unhandled rejection——Node 18+ 默认直接让进程退出。

- 反例：`doAsync()` 单独一行
- 正例：`await doAsync()` / `void doAsync().catch(err => log.error(...))`

## S3. 循环里不串行 await（1+N 的 JS 版）

`for (const id of ids) { await fetchOne(id) }` 会把 N 次请求串起来。改用 `Promise.all(ids.map(...))`；量大时用并发上限池，别一次打爆下游。

## S4. 错误对象整体交给日志，不要只打 message

`console.error(err.message)` 丢掉堆栈和 cause。传整个 error 对象；跨层抛出时用 `new Error("上下文", { cause: err })` 保留链路。

## S5. 捕获要精确，不吞错

禁止空 `catch {}`。`try` 块只包住可能抛错的那几行，不要整个函数体裹一层。

## S6. 模块顶层不做副作用 I/O

顶层只做定义与导出；连接、读配置、发请求放进显式的初始化函数，避免 import 顺序决定运行结果。

## S7. 对外数据必须校验后再用

接口返回、`JSON.parse` 结果、用户输入在使用前先校验形状与必填字段，不要直接深层解构后透传到下游。
