# 计算器 Web App 架构设计

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v0.1（草案，待评审） |
| 日期 | 2026-10-26 |
| 负责人 | designer（团队 clawteam-docker） |
| 任务 | 335f5d96 — 第一阶段：需求调研 + 架构设计 |
| 状态 | 待 leader / 实现方 / QA 评审 |
| 关联文档 | [requirements.md](./requirements.md) |
| 本阶段范围 | 只交付设计文档；除 `docs/` 外不创建实现文件 |

> 本文描述目标架构与关键决策，不包含功能实现。目录结构是给实现阶段的建议骨架，本阶段不落地代码。

---

## 1. 架构目标与约束

| 目标 | 约束/落点 |
| --- | --- |
| 零运行时依赖 | 原生 HTML/CSS/JS（ES Modules），无框架、无构建、无 CDN |
| 计算与 UI 分离 | `core/` 纯函数，不引用 DOM；UI 只消费状态并派发动作 |
| 可测试 | 分词、解析、求值、格式化、reducer 全部可在 Node 22 `node --test` 下直接测试 |
| 安全 | 禁止 `eval` / `new Function`；自建分词 + 递归下降；严格 CSP；无网络请求 |
| 可预测 | 所有输入规则、错误码、显示格式都有显式定义与用例 |
| 响应式 | 同一套 DOM/CSS 适配 320px 手机到桌面双栏 |
| 可降级 | `localStorage` 失败不影响计算；无外部资源 |
| 小体积 | 目标 < 60 KB 未压缩；无图片、无字体文件 |

**平台事实（本容器已核实，2026-10-26）**

- Node `v22.23.4`；`node --test` 冒烟测试通过（1 pass / 0 fail）。
- `npm registry` 可达（HTTP 200），但本设计仍选择零依赖：避免安装步骤、供应链风险与版本漂移。
- MDN 的 `eval`、`Number`、`toPrecision`、CSP 条目可达；交互类官方资料未能联网核实（详见需求文档 §4.1）。

---

## 2. 技术选型

| 决策点 | 选择 | 主要理由 | 放弃的替代方案 |
| --- | --- | --- | --- |
| UI 框架 | 原生 DOM + ES Modules | 页面只有一组键盘、一个显示区、一个历史列表；引入框架会增加体积、构建与依赖 | React/Vue/Svelte：对本期规模过重 |
| 语言 | JavaScript（ES2022）+ JSDoc 类型注释 | 无转译、无构建；编辑器仍可获得类型提示 | TypeScript：需要编译步骤或运行时转译 |
| 表达式求值 | 自建分词器 + 递归下降解析器 | 可测试、可定位错误、满足 CSP、无代码注入面 | `eval` / `new Function` / `math.js`：安全或依赖问题 |
| 数值模型 | IEEE-754 `number` + 展示层 15 位有效数字稳定化 | 零依赖、性能好、覆盖日常运算 | `decimal.js` / BigDecimal：增加依赖与体积；本期明确非金融级 |
| 测试 | Node 22 内置 `node --test` + `node:assert/strict` | 零依赖，已在本容器验证 | Jest/Vitest：需要 npm 安装 |
| 样式 | 原生 CSS（Grid/Flex + 自定义属性） | 无构建、易做响应式与深色模式 | Tailwind/CSS-in-JS：需要工具链 |
| 存储 | `localStorage`（50 条历史） | 数据量小、同步 API 简单、隐私边界清晰 | IndexedDB：本期过重；后端：超出范围 |
| 开发服务器 | 可选 `node:http` 静态服务器（`scripts/dev-server.mjs`） | 零依赖；仅本地开发用 | `npx serve` / Vite：引入 npm 依赖 |
| 部署 | 任意静态文件托管，相对路径 | 无后端、无路由、可放子路径 | SSR / 容器运行时：无必要 |

### 2.1 为什么不使用 `eval`

- MDN 明确警告 `eval` 会执行任意代码，存在安全风险，并带来性能与调试问题（<https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/eval>）。
- 用户输入进入 `eval` 会形成代码注入面；即使过滤，也难以覆盖所有构造。
- 自建解析器可以返回结构化错误、限制深度/长度、保证只支持白名单运算。
- 解析器同时服务于实时预览、历史重放与测试，边界更清晰。

> 实现约束：源码中不得出现 `eval(`、`new Function`、`setTimeout("...")`、`setInterval("...")`；CI/测试用静态扫描兜底。

---

## 3. 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│ index.html（静态语义结构：显示区 / 键盘 / 历史面板）          │
└───────────────┬─────────────────────────────────────────────┘
                │ DOM events
┌───────────────▼─────────────────────────────────────────────┐
│ ui/                                                          │
│  calculator-view.js  渲染状态、按钮事件委托                  │
│  keyboard.js         event.key → action                      │
│  history-view.js     历史列表渲染、点击/清空                 │
└───────────────┬─────────────────────────────────────────────┘
                │ dispatch(action) / subscribe(state)
┌───────────────▼─────────────────────────────────────────────┐
│ app/                                                         │
│  store.js        订阅、启动水合、持久化副作用                │
│  state.js        初始状态 + 纯 reducer（输入规则/状态机）    │
│  actions.js      动作常量/构造器（可选）                     │
└───────┬───────────────────────────────┬─────────────────────┘
        │ 纯函数调用                     │ 读写（注入）
┌───────▼─────────────────────┐  ┌──────▼─────────────────────┐
│ core/（无 DOM、无存储）      │  │ storage/history-store.js   │
│  tokenizer.js               │  │  localStorage 适配器        │
│  parser.js                  │  │  校验/上限/异常捕获         │
│  evaluator.js               │  └────────────────────────────┘
│  formatter.js               │
│  serializer.js（表达式显示）│
│  limits.js / errors.js      │
└─────────────────────────────┘
```

**依赖方向（单向，禁止回指）**

```
core  ←  app  ←  ui
core  ←  app  →  storage
main.js 负责组装：创建 store、注入 historyStore、绑定 UI 与键盘
```

- `core/` 不得引用 `window`、`document`、`localStorage`。
- `app/state.js` 只做纯状态变换；持久化放在 `store.js` 的副作用层。
- `ui/` 不得直接调用 `core` 求值来「绕过状态」；预览由 store/reducer 计算。
- `storage/` 不依赖 `core`；只负责序列化历史数组。

---

## 4. 建议目录结构（实现阶段落地，本阶段不创建）

```
calculator-app/
├── docs/
│   ├── requirements.md
│   └── architecture.md
├── index.html                 # 静态结构：显示区、键盘、历史面板、CSP meta
├── package.json               # {"type":"module"}；scripts: test/start；无 dependencies
├── scripts/
│   └── dev-server.mjs         # 可选：node:http 静态服务器，仅开发用
├── src/
│   ├── main.js                # 组装：加载历史、创建 store、绑定视图与键盘
│   ├── app/
│   │   ├── actions.js         # 动作类型与构造器
│   │   ├── state.js           # 初始状态、纯 reducer、预览计算
│   │   └── store.js           # subscribe/dispatch、持久化副作用、水合
│   ├── core/
│   │   ├── tokenizer.js       # 字符流 → Token[]
│   │   ├── parser.js          # Token[] → AST（递归下降）
│   │   ├── evaluator.js       # AST → 数值结果 / 结构化错误
│   │   ├── formatter.js       # number → 展示字符串（15 位有效数字）
│   │   ├── serializer.js      # Token[] → 表达式显示字符串
│   │   ├── limits.js          # 长度/深度/位数常量与检查
│   │   └── errors.js          # 错误码、错误对象、中文文案
│   ├── ui/
│   │   ├── calculator-view.js # 渲染显示区、键盘事件委托、状态样式
│   │   ├── keyboard.js        # 物理键盘映射、preventDefault、IME 防护
│   │   ├── history-view.js    # 历史列表、清空确认、移动端开合
│   │   └── dom.js             # 小型 textContent/元素创建辅助
│   ├── storage/
│   │   └── history-store.js   # localStorage 适配、校验、容量、降级
│   └── styles/
│       └── main.css           # 布局、主题、响应式、焦点、深色模式
└── test/
    ├── tokenizer.test.js
    ├── parser.test.js
    ├── evaluator.test.js
    ├── formatter.test.js
    ├── serializer.test.js
    ├── state.test.js
    ├── history-store.test.js
    ├── limits.test.js
    └── no-eval.test.js        # 静态扫描源码禁用项
```

**文件职责边界**

| 文件 | 输入 | 输出 | 禁止 |
| --- | --- | --- | --- |
| `tokenizer.js` | 字符串 | `{ok, tokens}` / `{ok:false, error}` | DOM、求值 |
| `parser.js` | Token[] | `{ok, ast}` / `{ok:false, error}` | 求值、DOM |
| `evaluator.js` | AST | `{ok, value}` / `{ok:false, error}` | 格式化、DOM |
| `formatter.js` | number | display string | 求值、DOM |
| `serializer.js` | Token[] | 表达式显示串 | DOM |
| `state.js` | state + action | 新 state | 存储、DOM |
| `store.js` | 依赖注入 | 订阅/派发 API | 直接操作 DOM |
| `history-store.js` | storage 适配器 | 历史数组/可用标志 | 计算逻辑 |
| `calculator-view.js` | state | DOM 更新 | 解析/求值 |
| `keyboard.js` | KeyboardEvent | action | 直接改状态 |

---

## 5. 核心模块设计

### 5.1 词法分析（tokenizer）

**词法单元**

| 类型 | 内部规范值 | 说明 |
| --- | --- | --- |
| `num` | `raw: string`（如 `"12.5"`、`"1e+16"`） | 不在此阶段转 number，保留原文便于显示/错误定位 |
| `op` | `+` `-` `*` `/` | 内部统一 ASCII |
| `lparen` | — | `(` |
| `rparen` | — | `)` |
| `percent` | — | `%` |

**规范化**

- 显示符号 `×` → `*`、`÷` → `/`、`−`（U+2212）→ `-`；同时接受 ASCII。
- 忽略空白字符（历史重放/未来粘贴兼容）。
- 数字词法（见 §6.6）：支持 `123`、`12.5`、`.5`、`5.`、科学计数 `1.2e+16`；UI 不提供 `e` 键，科学计数仅用于结果回填/历史重放。
- 未知字符返回 `E_SYNTAX`，带 `position`；不抛异常。
- 输出形如：`{type:"num", raw:"12.5", start:0, end:4}`，供错误定位。

**接口**

```js
tokenize(input: string) -> {ok: true, tokens: Token[]}
                       | {ok: false, error: CalcError}
```

### 5.2 语法分析（parser，递归下降）

**文法**

```
expression     := additive EOF
additive       := multiplicative (("+" | "-") multiplicative)*
multiplicative := unary (("*" | "/") unary)*
unary          := ("+" | "-") unary | postfix
postfix        := primary "%"*
primary        := NUMBER | "(" expression ")"
NUMBER         := (DIGIT+ ("." DIGIT*)? | "." DIGIT+)
                  (("e" | "E") ("+" | "-")? DIGIT+)?
```

**优先级（高 → 低）**

1. 括号 / 数字字面量
2. 后缀 `%`
3. 一元 `+` / `-`
4. `*` `/`（左结合）
5. `+` `-`（左结合）

> 注：文法中 `unary` 包裹 `postfix`，因此 `-3%` 解析为 `-(3%) = -0.03`，符合需求 §7.3。

**AST 节点**

```js
{type:"num", value: number, raw: string}
{type:"unary", op:"+"|"-", operand: Node}
{type:"percent", operand: Node}
{type:"binary", op:"+"|"-"|"*"|"/", left: Node, right: Node}
```

**规则**

- 不做隐式乘法：`2(3+4)`、`2%3`、`)` 后接数字均在解析时报错。
- 括号必须成对；空括号 `()` 报错。
- 嵌套深度上限 16（在解析时计数，超限返回 `E_TOO_DEEP`）。
- 数字原文转 `Number` 后必须有限；`1e999` 等返回 `E_OVERFLOW`。
- 错误对象包含 `code`、`message`、`position`；不抛出。

**接口**

```js
parse(tokens: Token[]) -> {ok: true, ast: Node}
                       | {ok: false, error: CalcError}
```

### 5.3 求值（evaluator）

**接口**

```js
evaluate(ast: Node) -> {ok: true, value: number}
                    | {ok: false, error: CalcError}
```

**规则**

| 运算 | 规则 | 错误 |
| --- | --- | --- |
| `num` | `Number(raw)`；必须 `Number.isFinite` | `E_OVERFLOW` |
| `unary +` | 直接返回操作数 | — |
| `unary -` | `-operand`（正确处理 `-0`） | — |
| `percent` | `operand / 100`；可连续 | — |
| `+ - *` | 双精度计算；结果必须有限 | `E_OVERFLOW` |
| `/` | 先检查 `right === 0`（含 `-0`） | `E_DIV_ZERO` |
| `/` | 结果必须有限 | `E_OVERFLOW` |
| 任意 | 结果 `NaN` 一律视为错误（防御性） | `E_UNKNOWN` |

- **逐节点检查**：每个二元运算后立即检查有限性，避免 `Infinity - Infinity` 产生 `NaN`。
- **下溢**：结果变为 `0` 或次正规数时不报错；`formatter` 显示 `0`（见 §6.5）。
- **负零**：求值可产生 `-0`；`formatter` 归一化为 `0`。
- **不短路**：表达式已解析为树，按规定顺序求值；错误位置由解析阶段提供。

### 5.4 格式化（formatter）

**接口**

```js
formatNumber(value: number) -> string   // 调用方保证 finite
```

**算法**

1. 若 `Object.is(value, -0)`，返回 `"0"`。
2. `normalized = Number(value.toPrecision(15))`，即保留 15 位有效数字后回到 number，消除 `0.30000000000000004` 一类展示噪声。
3. 记 `abs = Math.abs(normalized)`：
   - 若 `abs === 0`，返回 `"0"`。
   - 若 `abs >= 1e16` 或 `abs < 1e-6`：使用科学计数法，尾数最多 15 位有效数字、去掉尾随 0，指数写为 `e+16` / `e-7`（不补前导零）。
   - 否则：返回 `String(normalized)`（该区间内 JS 输出为普通十进制，不含 `e`）。
4. 输出只使用 `.` 作为小数点；不加千分位；不使用本地化分隔符。

**示例**

| 输入值 | 输出 |
| --- | --- |
| `0.30000000000000004` | `0.3` |
| `1/3` | `0.333333333333333` |
| `-0` | `0` |
| `1e16` | `1e+16` |
| `1.5e16` | `1.5e+16` |
| `1e-6` | `0.000001` |
| `1e-7` | `1e-7` |
| `123.45700000000001` | `123.457` |
| `999999999999999` | `999999999999999` |

**精度边界（写入用户可见说明/README）**

- 内部为 IEEE-754 双精度，约 15–17 位十进制有效数字；展示层固定 15 位。
- 不适用于金融结算、法定计量、需要十进制精确相等的场景。
- `0.1 + 0.2 = 0.3` 是展示层稳定化结果，不等于二进制浮点内部精确相等。

### 5.5 表达式序列化（serializer）

**接口**

```js
serialize(tokens: Token[]) -> string   // 用于表达式行与历史存储
```

- 运算符显示为 `+ − × ÷`；一元负号也显示为 `−`。
- 二元运算符两侧加空格，例如 `3 + 4 × 2`；一元负号与操作数之间不加空格，例如 `−3%`、`−(2 + 3)`。
- 括号内不额外加空格（`(2 + 3)`）；`%` 紧贴操作数。
- 序列化结果必须能被 `tokenize` 重新解析（历史重放）。
- 实现建议：按 token 顺序输出，利用「上一个有效 token 是否为操作数结束」判断当前 `-` 是二元还是一元，仅在二元时补空格。

### 5.6 UI 层

**`calculator-view.js`**

- 启动时缓存 DOM 引用；订阅 store。
- 每次状态变化只更新：
  - 表达式行 `textContent`（横向滚动到最右）。
  - 结果/预览行 `textContent` + 状态类名（预览弱化、错误红色）。
  - 错误区 `textContent` / `role="alert"`。
  - 运算符按钮的激活样式（当前表达式末尾为某运算符时）。
  - 历史列表仅在 `history` 引用变化时重绘。
- 键盘按钮使用事件委托：`data-action` / `data-value`。
- 不重建键盘 DOM，避免按键时丢失焦点。
- 历史渲染只用 `textContent`，禁止 `innerHTML`。

**`keyboard.js`**

- 监听 `document` 的 `keydown`。
- 忽略：`event.isComposing`、`event.altKey`、`event.ctrlKey`、`event.metaKey`（本期无组合快捷键）。
- 仅对已映射按键调用 `preventDefault()`，避免影响页面其他行为。
- 映射详见 §9。

**`history-view.js`**

- 桌面：右侧常驻面板；移动：折叠面板/底部抽屉（具体样式实现阶段定，但必须可键盘触发）。
- 每条记录渲染为 `<button>`：上行表达式、下行结果；`aria-label` 包含完整内容。
- 点击 → `loadHistory(id)`；清空按钮 → 二次确认后 `clearHistory()`。
- 空状态文案：「暂无历史记录」。

### 5.7 存储层

`history-store.js` 采用适配器注入，便于测试：

```js
createHistoryStore(storageLike) -> {
  load(): {entries: HistoryEntry[], available: boolean},
  save(entries: HistoryEntry[]): boolean,
  clear(): boolean
}
```

- `storageLike` 只需实现 `getItem` / `setItem` / `removeItem`；测试传入内存假对象。
- 所有访问包在 `try/catch`；`JSON.parse` 失败、结构不合法、版本不符 → 返回空历史 + `available` 保持可用（仅在写入抛错时标记不可用）。
- 不在这里做去重/截断（由 reducer/append 逻辑负责），但 `save` 前仍会校验长度上限，防御性截断。

---

## 6. 关键语义决策

### 6.1 表达式模式与求值时机

- 采用**表达式模式**：按键只编辑表达式；实时预览按当前表达式计算；按 `=` 才提交结果并写入历史。
- 不做立即执行模式；不在按键时产生副作用式中间结果。
- 预览失败（不完整/除零等）时静默，不进入错误态；只有 `=` 才展示错误。

**理由**：与自建解析器一致；用户能看到完整表达式；状态更少；测试更直接。代价是与部分四则计算器手感不同（需求 §4.2）。

### 6.2 百分号

- `x%` 一律等于 `x / 100`，后缀、左结合、可叠加。
- `50 + 10%` = `50.1`；`50 × 10%` = `5`；`50%%` = `0.005`。
- `%` 可作用于数字、括号整体、已有百分号结果。
- 不实现上下文百分号（`50 + 10%` = 55 的语义）。

**理由**：单一规则、可写成表驱动测试、与表达式模式一致。**风险**：与部分用户直觉不一致，见需求 OQ-1；若产品改口径，需要改 parser/evaluator 的求值语义（上下文百分号依赖左操作数与运算符），并同步测试、文案与验收用例。

### 6.3 一元负号

- 位置决定语义：表达式开头、`(` 后、二元运算符后出现 `-` → 一元；操作数后出现 `-` → 二元。
- 一元负号右结合、可叠加：`--3` = `3`；`2--3` = `5`；`-(2+3)` = `-5`。
- 与 `%` 组合：`-3%` = `-0.03`（一元作用于百分号结果）。
- `±` 作用于「当前操作数」：
  - 编辑态：找到当前操作数起点（末尾为数字/`%`/`)` 时向前匹配），插入或移除一元负号。
  - 求值态：以结果构造 `-<result>` 进入编辑态。
  - 空态/操作符后：插入一元负号。

**输入层规则（append-only，无光标）**

| 场景 | 按 `−` 的行为 |
| --- | --- |
| 空表达式 | 插入一元负号 |
| 末尾是 `+ * /` | 插入一元负号（支持 `5×−2`） |
| 末尾是 `-` | 再插入一个一元负号（`−−`） |
| 末尾是 `(` | 插入一元负号 |
| 末尾是数字/`%`/`)` | 插入二元减号 |

> 副作用：若用户想用 `−` 替换上一個 `×`，会得到 `× −`。这是为支持自然输入 `5×−2` 的取舍；需要改运算符时可先 `DEL`。实现阶段如需更聪明的「替换 vs 一元」判定，必须在测试中补齐并更新本文档。

### 6.4 括号与隐式乘法

- 括号支持嵌套，深度上限 16。
- 不支持隐式乘法：`2(3+4)`、`(1+2)(3+4)`、`2 3` 均报错。
- `)` 只有在括号栈非空且前一 token 是操作数结束（数字/`%`/`)`）时才允许输入。
- `(` 只允许在表达式开头、运算符后、`(` 后输入。

### 6.5 数值、精度与显示

| 项 | 决策 |
| --- | --- |
| 内部数值 | IEEE-754 binary64（JS `number`） |
| 展示有效数字 | 15 位 |
| 稳定化 | `Number(x.toPrecision(15))` 后再格式化 |
| 科学计数阈值 | 绝对值 `>= 1e16` 或 `0 < 绝对值 < 1e-6` |
| 负零 | 显示 `0` |
| 千分位 | 不使用 |
| 小数分隔符 | `.` |
| 下溢 | 允许变为 0/次正规数，显示 `0`，不报错 |
| 溢出 | 报 `E_OVERFLOW`，不显示 `Infinity` |
| 金融级精度 | 明确不支持（需求 §10） |

**为什么不引入十进制库**

- 需求限定零依赖、小体积、日常计算；`decimal.js` 会增加数十 KB 与依赖管理。
- 采用十进制库仍要定义除法精度、舍入模式、科学计数展示，验收面更大。
- 若未来要做财务模式，应作为独立需求评估，而不是悄悄替换数值模型。

### 6.6 数字字面量规则

- 允许：`123`、`12.5`、`.5`（内部补 `0.` 显示）、`5.`（显示 `5.`，求值 `5`）、`1e+16`（仅结果回填/历史）。
- 不允许：`1.2.3`、`1e`、`e10`、全角数字、`NaN`、`Infinity`。
- 有效数字上限 15：
  - 统计方法：去掉小数点与非数字，去掉前导 0；空串按 1 位计。
  - 例：`0.0001` → 1 位；`1000000000000000`（16 位）→ 超限；`1.000000000000000`（16 位）→ 超限。
- 单字面量字符长度上限 32（含小数点，不含科学计数符号；结果回填时按生成串长度校验）。
- 输入层阻止超限；tokenizer 对历史/回填数据再次校验，超限返回 `E_NUMBER_TOO_LONG`。

### 6.7 显示与编辑的单一事实源

- **状态中的 `tokens` 是唯一事实源**；表达式显示、预览、求值都从 tokens 派生。
- 不维护「显示字符串 + 游标」双份状态；本期无光标编辑，只支持末尾追加与退格。
- `result` 是求值成功后的数值快照；`resultText` 是格式化后的字符串，用于显示与继续计算时回填。

---

## 7. 错误处理与上限

### 7.1 错误码

| 错误码 | 触发条件 | 用户文案（中文） | 可恢复方式 |
| --- | --- | --- | --- |
| `E_SYNTAX` | 无法分词、表达式不完整、非法 token 顺序 | 表达式不完整或有误 | 编辑/AC |
| `E_UNBALANCED_PAREN` | 括号不匹配、空括号 | 括号不匹配 | 编辑/AC |
| `E_IMPLICIT_MUL` | `2(3)`、`)` 后数字、`%` 后数字等 | 不支持省略乘号，请使用 × | 编辑/AC |
| `E_DIV_ZERO` | 除数为 `0` 或 `-0` | 不能除以零 | 编辑/AC |
| `E_OVERFLOW` | 字面量或运算结果非有限 | 结果超出可表示范围 | 编辑/AC |
| `E_TOO_LONG` | 表达式超 128 字符 | 表达式过长 | 编辑/AC |
| `E_TOO_DEEP` | 括号嵌套超 16 层 | 括号嵌套过深 | 编辑/AC |
| `E_NUMBER_TOO_LONG` | 数字有效位/长度超限 | 单个数字最多 15 位有效数字 | 编辑/AC |
| `E_UNKNOWN` | 防御性兜底（NaN 等） | 无法计算，请检查输入 | 编辑/AC |

### 7.2 错误对象

```js
{
  code: "E_DIV_ZERO",
  message: "不能除以零",     // 用户可见
  position?: number,        // 字符索引，供开发调试；UI 可不展示
  detail?: string           // 开发信息，不直接渲染
}
```

- 所有核心函数返回 `{ok:false,error}`，不抛出异常。
- UI 层对未知异常做最后一道 `try/catch`，显示 `E_UNKNOWN` 文案，避免白屏。
- 错误对象不包含用户输入的 HTML 片段；即使包含，也只经 `textContent` 渲染。

### 7.3 上限常量（`limits.js`）

| 常量 | 值 | 检查位置 |
| --- | --- | --- |
| `MAX_NUMBER_SIG_DIGITS` | 15 | 输入层、tokenizer |
| `MAX_NUMBER_CHARS` | 32 | 输入层、tokenizer |
| `MAX_EXPRESSION_CHARS` | 128 | 输入层（序列化长度）、tokenizer |
| `MAX_PAREN_DEPTH` | 16 | 输入层、parser |
| `MAX_HISTORY_ENTRIES` | 50 | reducer/append、storage |
| `MAX_ID_LENGTH` | 64 | storage 校验 |
| `MAX_HISTORY_EXPRESSION_CHARS` | 128 | storage 校验 |
| `MAX_HISTORY_RESULT_CHARS` | 32 | storage 校验 |

- 超限输入在 UI 层直接忽略并给出一次性轻提示（不进入错误态）。
- 历史/回填数据超限在核心层返回错误，防止旧数据或手工篡改导致异常。

---

## 8. 状态管理

### 8.1 状态形状

```js
/**
 * @typedef {"empty"|"editing"|"evaluated"|"error"} Phase
 * @typedef {Object} CalcState
 * @property {Phase} phase
 * @property {Token[]} tokens              // 唯一输入事实源
 * @property {number|null} result          // 求值成功后的数值
 * @property {string|null} resultText      // 结果格式化串
 * @property {string|null} previewText     // 编辑态实时预览
 * @property {CalcError|null} error
 * @property {HistoryEntry[]} history      // 最新在前，最多 50
 * @property {boolean} storageAvailable    // localStorage 是否可写
 */
```

- `expressionText` 不存状态，由 `serialize(tokens)` 派生。
- 历史面板开合、当前聚焦按钮等属于 UI 局部状态，不进入 `CalcState`（除非实现阶段证明需要持久化）。

### 8.2 动作

| 动作 | 载荷 | 说明 |
| --- | --- | --- |
| `digit` | `"0".."9"` | 追加/替换数字 |
| `decimal` | — | 追加小数点 |
| `operator` | `"+"` `"-"` `"*"` `"/"` | 插入/替换二元运算符，或插入一元负号 |
| `percent` | — | 追加 `%` |
| `paren` | `"("` `")"` | 括号输入 |
| `toggleSign` | — | `±` |
| `evaluate` | — | `=` |
| `clearAll` | — | `AC` |
| `deleteBack` | — | `DEL` / Backspace |
| `loadHistory` | `id` | 历史条目载入编辑区 |
| `clearHistory` | — | 清空历史（UI 已确认） |
| `hydrateHistory` | `entries` | 启动时从存储水合 |
| `setStorageAvailable` | `boolean` | 存储写入失败/恢复 |

### 8.3 状态机

```
            digit / decimal / (
   empty ─────────────────────────▶ editing
     ▲                                │  │
     │ AC                             │  │ =（合法）
     │                                │  ▼
     │                             error ◀── =（非法）
     │                                │
     └────────── AC / digit ──────────┘
                                      evaluated
                                        │  digit → 新 editing
                                        │  operator/% → 以结果继续 editing
                                        │  DEL → 恢复表达式 editing
                                        │  AC → empty
```

**关键转移规则**

| 当前 | 动作 | 结果 |
| --- | --- | --- |
| `empty` | 数字 | `editing`，tokens=[num] |
| `empty` | `.` | `editing`，tokens=[num "0."] |
| `empty` | `−` | `editing`，tokens=[op "-"]（一元） |
| `empty` | `+ × ÷` / `%` / `)` | 忽略 |
| `empty` | `=` | 无操作（不写历史） |
| `editing` | 数字 | 追加到当前数字；必要时替换前导 0；超限忽略 |
| `editing` | 运算符 | 按 §6.3 与输入规则插入/替换 |
| `editing` | `%` | 末尾为数字/`%`/`)` 时追加，否则忽略 |
| `editing` | `=` 合法 | `evaluated`，保存 result/resultText，历史追加 |
| `editing` | `=` 非法 | `error`，保留 tokens，写 error |
| `evaluated` | 数字/`.`/`(` | `editing`，新表达式（旧结果作为历史已保存） |
| `evaluated` | 运算符 | `editing`，tokens=[num resultText, op] |
| `evaluated` | `%` | `editing`，tokens=[num resultText, percent] |
| `evaluated` | `±` | `editing`，tokens=[op "-", num resultText] |
| `evaluated` | `DEL` | `editing`，对原 tokens 执行删除 |
| `evaluated` | `=` | 无操作（不重复运算） |
| `error` | 数字/`.`/`(` | 清错，开始新表达式 `editing` |
| `error` | `AC` | `empty` |
| `error` | `DEL` | 删除最后 token，清错，`editing` |
| `error` | 运算符/`%`/`=` | 忽略 |
| 任意 | `loadHistory` | `editing`，tokens 由历史表达式解析；不自动求值 |
| 任意 | `clearHistory` | `history=[]`，其余不变 |

**历史追加规则**

- 仅 `evaluate` 成功时追加；预览、错误、AC、DEL 不写历史。
- 新条目：`{id, expression: serialize(tokens), result: resultText, createdAt: ISO-8601}`。
- 若最新条目的 `expression` 与 `result` 均相同，只更新 `createdAt`，不重复插入。
- 上限 50；超出时从尾部淘汰。
- 历史解析失败（理论上不应发生）→ 忽略该条目并保留其余。

### 8.4 Store 与副作用

```js
createStore({historyStore}) -> {
  getState(): CalcState,
  dispatch(action): void,
  subscribe(listener): () => void
}
```

- `dispatch` 内调用纯 `reduce`；若 `history` 引用变化，异步/同步调用 `historyStore.save(state.history)`；写入失败则 `dispatch(setStorageAvailable(false))`（避免递归需一次性标志）。
- 启动：`historyStore.load()` → `dispatch(hydrateHistory)`；`available=false` 时显示一次性提示「历史记录仅本次会话可用」。
- 不在每次按键保存历史；只在历史变化时保存。
- 订阅者异常不应阻塞其他订阅者（实现阶段可 `try/catch` 每个 listener）。

---

## 9. 键盘映射

| 物理按键（`event.key`） | 动作 | 备注 |
| --- | --- | --- |
| `0`–`9` | 数字 | 小键盘数字键同样产生 `0`–`9` |
| `.` | 小数点 | 小键盘 `.` 通常也是 `.` |
| `+` | 加 | 需 `Shift+=`，`event.key` 为 `+` |
| `-` | 减 / 一元负号 | 由位置决定 |
| `*`、`x`、`X` | 乘 | `x` 作为别名 |
| `/` | 除 | 必须 `preventDefault()`，避免 Firefox 快速查找 |
| `%` | 百分号 | `Shift+5` |
| `(`、`)` | 括号 | `Shift+9/0` |
| `Enter`、`=` | 求值 | `=` 为 `event.key === "="`；小键盘 Enter 为 `Enter` |
| `Backspace` | 退格 DEL | 必须 `preventDefault()`，避免浏览器后退 |
| `Escape`、`Delete` | AC | 两键均清空；`Delete` 不做 CE |
| `F9` | `±` | 与 Windows 计算器习惯一致（未联网核实，仅作便利键） |
| `h` / `H` | 开合历史 | 仅当焦点不在可编辑元素；P1 可选 |

**实现约束**

- 用 `event.key`，不用已废弃的 `keyCode`；小键盘通过同一 `key` 自然覆盖。
- `event.isComposing === true` 时忽略，避免中文输入法组合误触。
- 带 `ctrlKey` / `metaKey` / `altKey` 的组合一律不拦截（保留浏览器快捷键）。
- 仅对已处理的键调用 `preventDefault()`；未映射键不干扰。
- 历史面板打开时，`Escape` 优先关闭面板；面板关闭后 `Escape` 才执行 AC，避免一次按键触发两个行为。
- 键盘监听挂在 `document`；若未来出现输入框/对话框，需在目标为可编辑元素时提前返回。
- 所有键盘动作与按钮走同一个 `dispatch`，不复制业务逻辑。

---

## 10. 历史记录与持久化

### 10.1 存储键与结构

- 键：`calculator.history.v1`
- 值（JSON）：

```json
{
  "version": 1,
  "entries": [
    {
      "id": "0f0c9f7e-...",
      "expression": "3 + 4 × 2",
      "result": "11",
      "createdAt": "2026-10-26T15:50:00.000Z"
    }
  ]
}
```

- `id`：`crypto.randomUUID()`；不可用时降级 `Date.now().toString(36) + Math.random().toString(36).slice(2)`。
- 时间：ISO-8601 UTC 字符串；仅用于排序/显示（本期可不显示时间，但保留字段）。
- 不存中间状态、不存用户代理、不存任何可识别信息。

### 10.2 读写策略

| 场景 | 行为 |
| --- | --- |
| 启动 | `load()`：解析 → 校验 `version === 1`、`entries` 为数组 → 逐条校验字段类型/长度 → 截断到 50 条 |
| JSON 损坏/版本不符 | 返回空数组；不删除原键（下次成功写入时覆盖），不崩溃 |
| 新历史 | 成功求值后由 reducer 更新；store 检测引用变化后 `save()` |
| 写入抛错（配额/隐私模式） | 标记 `storageAvailable=false`；保留内存历史；UI 一次性提示 |
| 清空 | UI 二次确认 → `clearHistory` → `removeItem`；失败也清空内存并提示 |
| 隐私模式/禁用 | 同写入失败；历史仅在当前会话可用 |

### 10.3 历史交互

- 点击条目：解析 `expression` 为 tokens，进入编辑态；**不自动求值**（OQ-4 默认）。
- 若历史表达式无法解析（被篡改/旧版本）：忽略点击，UI 不崩溃。
- 清空：按钮 → 确认（原生 `confirm` 或应用内二次点击，实现阶段定）→ 清空。
- 移动端历史面板默认折叠；打开后焦点进入面板，`Escape` 关闭（不与 AC 冲突：面板打开时 `Escape` 先关面板，再按才 AC；实现阶段需明确）。
- 空历史显示占位文案，不渲染空列表容器。

---

## 11. UI、响应式与可访问性

### 11.1 页面结构（语义）

```html
<main>
  <section aria-label="计算器">
    <div class="display">
      <div class="expression" aria-label="表达式"></div>
      <output class="result" aria-live="polite"></output>
      <div class="error" role="alert"></div>
    </div>
    <div class="keypad" role="group" aria-label="计算器键盘">
      <!-- 22 个 button，带 data-action / data-value -->
    </div>
  </section>
  <aside aria-label="计算历史">
    <button class="history-toggle" aria-expanded="false">历史</button>
    <ul class="history-list"></ul>
    <button class="history-clear">清空历史</button>
  </aside>
</main>
```

**键盘布局（4 列 × 6 行，最后一行 `=` 跨 3 列）**

|  |  |  |  |
| --- | --- | --- | --- |
| AC | DEL | `(` | `)` |
| 7 | 8 | 9 | ÷ |
| 4 | 5 | 6 | × |
| 1 | 2 | 3 | − |
| ± | 0 | . | + |
| % | `=`（跨 3 列） |  |  |

- 所有按键使用 `<button type="button">`，不用 `div` 模拟。
- 运算符按钮 `aria-label`：`乘`、`除`、`减`、`加`、`百分号`、`正负号`、`退格`、`全部清除`。
- `=` 按钮跨列用 CSS Grid `grid-column: span 3`，不影响读屏顺序。

### 11.2 响应式

| 断点 | 布局 |
| --- | --- |
| `< 600px` | 单列：显示区 + 键盘占满宽度；历史为可开合面板/底部抽屉 |
| `600–899px` | 单列居中，最大宽度约 480px；历史折叠 |
| `>= 900px` | 双栏：左侧计算器（约 380–420px），右侧历史面板（约 280–320px） |

- 触控目标最小 44×44 CSS px；按键间距 ≥ 8px。
- 使用 `min-height: 100dvh`，回退 `100vh`；`padding` 使用 `env(safe-area-inset-*)`。
- 页面 `overflow-x: hidden` 仅作兜底；根本不能出现 320px 横向溢出。
- 字号用 `clamp()`；长结果自动缩小或横向滚动（结果行优先缩小字号，最低 24px）。
- 表达式行 `overflow-x: auto; white-space: nowrap; direction: ltr; text-align: right`。
- 深色模式：`@media (prefers-color-scheme: dark)` 覆盖 CSS 自定义属性；P1，不阻塞。
- 减少动画：`@media (prefers-reduced-motion: reduce)` 去掉过渡。

### 11.3 可访问性

- 结果 `<output aria-live="polite">`；预览不加 live（避免每键播报）；按 `=` 后结果变化才播报。
- 错误容器 `role="alert"`；错误出现时读屏立即播报。
- 表达式区可加 `aria-label="表达式"`，但不设为 live。
- 焦点可见：`:focus-visible` 2px 高对比轮廓；不用 `outline: none` 而无替代。
- 对比度：正文与按钮文字达 WCAG 2.1 AA（4.5:1；大字号 3:1）。
- 所有功能可仅用键盘完成；Tab 顺序与视觉顺序一致。
- 不用颜色作为唯一状态提示：错误同时有文案；当前运算符同时有边框/形状变化。
- 历史条目是按钮，`aria-label` 包含表达式与结果。
- 移动端历史面板打开时管理焦点；关闭后焦点回到触发按钮。
- 不自动播放动画/声音；无音频反馈。

---

## 12. 安全与隐私

### 12.1 禁用项

- `eval`、`new Function`、`Function("...")`、`setTimeout("...")`、`setInterval("...")`。
- `innerHTML` / `outerHTML` / `insertAdjacentHTML` 插入用户输入或历史内容。
- 外部脚本、字体、图标、图片、统计 SDK、远程 API。
- Cookie、`sessionStorage` 之外的追踪标识（本期只用 `localStorage` 存历史）。
- 内联事件处理器（`onclick="..."`）与内联 `<style>`，以配合严格 CSP。

### 12.2 CSP

`index.html` 内 meta 兜底：

```html
<meta http-equiv="Content-Security-Policy"
      content="default-src 'self'; script-src 'self'; style-src 'self';
               img-src 'self' data:; font-src 'self'; connect-src 'none';
               object-src 'none'; base-uri 'none'; form-action 'none'">
```

- `frame-ancestors` 不能通过 meta 生效；部署方应通过 HTTP 响应头补充：

```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self';
  img-src 'self' data:; font-src 'self'; connect-src 'none'; object-src 'none';
  base-uri 'none'; form-action 'none'; frame-ancestors 'none'
```

- 若部署环境无法设置响应头，meta 仍能阻断外部脚本与网络请求；`frame-ancestors` 缺失作为已知限制记录。
- 不使用内联脚本，因此无需 `'unsafe-inline'`。

### 12.3 隐私

- 历史仅存本机；不采集、不上传、不跨站共享。
- 清空历史会删除对应 `localStorage` 键。
- 页面无登录、无 Cookie、无指纹采集。
- 错误信息不包含用户输入以外的环境信息。

---

## 13. 测试策略

### 13.1 单元测试（Node 22 `node --test`）

运行：

```bash
node --test
# 覆盖率（本容器 Node v22.23.4 已验证可用）
node --test --experimental-test-coverage
```

测试文件与被测模块一一对应，全部使用 `node:assert/strict`。

| 测试文件 | 覆盖点 |
| --- | --- |
| `tokenizer.test.js` | 数字/小数/科学计数、`×÷−` 归一化、空白、未知字符、位置、超长数字 |
| `parser.test.js` | 优先级、左结合、括号、嵌套上限、一元负号、百分号、隐式乘法、空表达式、括号不匹配 |
| `evaluator.test.js` | §7.1/§7.2/§7.3 全部用例、除零、`-0`、溢出、下溢、连续百分号 |
| `formatter.test.js` | 15 位有效数字、`0.1+0.2`、`1/3`、科学计数阈值、负零、边界值 |
| `serializer.test.js` | 一元/二元负号空格、括号、百分号、可重新 tokenize（round-trip） |
| `state.test.js` | 输入规则、前导零、小数点、运算符替换、求值后继续、错误恢复、`±`、DEL、历史追加/去重/上限 |
| `history-store.test.js` | 正常读写、损坏 JSON、版本不符、字段非法、配额异常、清空、50 条截断 |
| `limits.test.js` | 15 位有效数字计数、32 字符、128 字符表达式、16 层括号 |
| `no-eval.test.js` | 读取 `src/**/*.js`，断言无 `eval` / `new Function` / 字符串定时器 / `innerHTML` 写入用户数据 |

**表驱动用例**：需求文档 §7 的每一条示例都进入测试；测试名包含输入与期望，失败时可直接定位语义。

**round-trip 测试**：对一组表达式执行 `tokenize → serialize → tokenize`，断言 token 序列等价，保证历史重放可靠。

### 13.2 手动/浏览器验收

由于零依赖不引入 Playwright/jsdom，UI 层采用人工清单（需求 §9）：

- 桌面：Chrome/Edge、Firefox、Safari；键盘全流程；`/` 与 Backspace 不触发浏览器行为。
- 手机：iOS Safari、Android Chrome；320/375/414 宽度；安全区；横竖屏。
- 读屏：VoiceOver 或 NVDA；结果只播报一次；错误可读；历史条目可操作。
- 存储：正常、隐私模式、配额满、手工写入损坏 JSON。
- 安全：Network 面板零第三方请求；CSP 控制台无违规；源码扫描通过。
- 离线：页面加载后断网，计算/历史仍可用。

### 13.3 CI 建议（实现阶段）

```bash
node --test
node -e "..."   # 或 test/no-eval.test.js 作为普通测试
```

- 无 `npm install` 步骤；Node 22 镜像直接运行。
- 可在 CI 中额外执行 `grep -R "eval(" src` 作为双保险。
- 不引入浏览器矩阵自动化；如需，另立需求评估 Playwright 依赖。

---

## 14. 性能预算

| 指标 | 目标 | 手段 |
| --- | --- | --- |
| 传输体积（HTML+CSS+JS，未压缩） | < 60 KB | 无框架、无图片、无字体、代码精简 |
| 首次可交互 | < 1 s（中端手机） | 静态文件、少量模块、无阻塞脚本 |
| 按键反馈 | < 50 ms | 只更新文本；不重排键盘；历史仅在变化时重绘 |
| 求值 | < 5 ms | 递归下降 + 单次遍历；表达式上限 128 字符 |
| 内存 | 常量级 | 历史最多 50 条；AST 不保留（除调试） |
| localStorage 写入 | 仅历史变化时 | 不在每次按键写入 |

- ES Modules 使用 `<script type="module" src="./src/main.js"></script>`；浏览器按依赖加载。
- 无构建、无压缩要求；若部署方启用 gzip/brotli 更好。
- 避免在 keydown 中同步读取布局（`offsetWidth` 等）；必要时用 `requestAnimationFrame` 批量更新。
- 预览计算开销小，无需防抖；若未来支持更长表达式，再评估防抖。

---

## 15. 浏览器兼容

| 能力 | 最低要求 | 回退 |
| --- | --- | --- |
| ES Modules | Safari 10.1+ / 所有现代浏览器 | 不支持则整页不可用（明确不支持旧浏览器） |
| `crypto.randomUUID` | Safari 15.4+ / Chrome 92+ | 时间戳 + 随机串降级 |
| `dvh` | Safari 15.4+ / Chrome 108+ | 先写 `100vh` 再写 `100dvh` |
| `env(safe-area-inset-*)` | iOS 11+ | 不支持时为 0 |
| `:focus-visible` | 现代浏览器 | 可加 `:focus` 兜底 |
| `prefers-color-scheme` | 现代浏览器 | 默认浅色 |
| `Intl` | 非硬依赖 | 本期不用 `Intl` 做数字格式化 |
| CSS Grid / 自定义属性 | 所有目标浏览器 | 无 |

- 目标：Chrome/Edge/Firefox 最近两个稳定版；Safari/iOS Safari 16.4+。
- 不引入 polyfill（避免依赖与体积）；低于矩阵的浏览器不保证。
- 不使用 `structuredClone`、`Array.prototype.group` 等较新 API，除非实现阶段确认矩阵。

---

## 16. 部署

| 项 | 约定 |
| --- | --- |
| 产物 | `index.html` + `src/**` + `styles/**`；无构建产物 |
| 路径 | 全部相对路径（`./src/...`），支持部署在子路径 |
| MIME | `.js` → `text/javascript`；`.css` → `text/css`；`.html` → `text/html` |
| 缓存 | HTML `Cache-Control: no-cache`；静态资源短缓存（如 `max-age=300`）或由部署方指纹化 |
| HTTPS | 建议强制；`localStorage` 在 `file://` 下行为不可靠，需通过 HTTP(S) 访问 |
| 本地开发 | `node scripts/dev-server.mjs`（可选，`node:http` 静态服务器） |
| 头部 | 建议配置 §12.2 的 CSP、`X-Content-Type-Options: nosniff`、`Referrer-Policy: no-referrer` |
| 无路由 | 单页无客户端路由，不需要 SPA fallback |
| 无 SW | 本期不注册 Service Worker；不做离线首次加载 |

---

## 17. 风险与缓解

| 风险 | 可能性 | 影响 | 缓解 |
| --- | --- | --- | --- |
| 百分号语义与产品预期不符 | 中 | 高 | OQ-1 先拍板；测试锁定；如需上下文语义，改 evaluator + 测试 + 文案 |
| 浮点展示被误认为计算错误 | 中 | 中 | 15 位稳定化；文档声明；边界测试；错误文案不暴露二进制细节 |
| UI 无自动化测试 | 高 | 中 | 核心纯函数覆盖；reducer 测试；人工清单 + 设备矩阵 |
| 键盘冲突（`/`、Backspace） | 中 | 低 | 仅处理已映射键并 `preventDefault`；真实浏览器冒烟 |
| `localStorage` 不可用 | 中 | 低 | 内存降级 + 一次性提示；读写全捕获 |
| 历史数据被篡改/旧版本 | 低 | 低 | 版本 + 字段校验；解析失败忽略条目 |
| 无构建导致模块请求多 | 低 | 低 | 控制模块数量；HTTP/2；本地/生产均可接受 |
| 多 worker 并行冲突 | 中 | 中 | 本阶段仅 `docs/`；实现阶段按 `core/app/ui/storage/test` 分工 |
| 兼容性低估 | 低 | 中 | 目标矩阵写死；实现前确认；不使用过新 API |
| 范围蔓延 | 中 | 中 | 需求 §10 排除清单；变更走新任务 |

---

## 18. 决策记录（ADR 摘要）

| ID | 决策 | 状态 | 备注 |
| --- | --- | --- | --- |
| ADR-001 | 原生 HTML/CSS/JS + ES Modules，零依赖、无构建 | 已定 | 规模小；避免供应链与工具链 |
| ADR-002 | 自建 tokenizer + 递归下降 parser，禁止 `eval` | 已定 | 安全、可测试、可定位错误 |
| ADR-003 | IEEE-754 双精度 + 展示 15 位有效数字 | 已定 | 非金融级；下溢/边界已定义 |
| ADR-004 | 表达式模式（支持优先级/括号），非立即执行 | 已定 | 与解析器一致；UI 差异见需求 §4 |
| ADR-005 | 百分号统一 `/100` | 暂定 | 待 OQ-1 产品确认；改动影响 evaluator/测试/文案 |
| ADR-006 | 历史用 `localStorage`，上限 50，版本化 | 已定 | 失败降级；无同步 |
| ADR-007 | 纯 core + 纯 reducer + 注入式存储 + 被动视图 | 已定 | 便于 Node 测试；UI 不持有业务规则 |
| ADR-008 | MVP 不做 Service Worker / PWA | 已定 | 避免缓存与更新复杂度；需求 §10 |
| ADR-009 | 不用浏览器自动化测试框架 | 暂定 | 零依赖；风险由人工清单承担 |

---

## 19. 待确认问题

| ID | 问题 | 架构默认 | 影响 |
| --- | --- | --- | --- |
| OQ-1 | 百分号严格 `/100` vs 上下文语义 | 严格 `/100` | evaluator 规则、验收用例、文案 |
| OQ-2 | 是否只做 zh-CN | 是 | 文案、数字格式；不做 i18n 框架 |
| OQ-3 | 深色模式是否进 MVP | P1，跟随系统 | CSS 变量与验收项 |
| OQ-4 | 历史点击载入表达式还是结果 | 载入表达式 | `loadHistory` 行为、测试 |
| OQ-5 | 是否需要复制结果 | 本期不做 | 剪贴板 API 与权限提示 |
| OQ-6 | 部署路径/CSP 响应头归属 | 相对路径 + meta CSP | 部署配置、`frame-ancestors` 限制 |
| OQ-7 | 浏览器最低版本 | 最近两个稳定版 / Safari 16.4+ | API 选择与回退 |

---

## 20. 实现阶段拆分建议（供 leader 派工）

| 工作包 | 内容 | 依赖 | 建议并行 |
| --- | --- | --- | --- |
| W1 | `core/tokenizer + parser + evaluator + formatter + serializer + errors/limits` | 无 | 是 |
| W2 | `app/state + store + storage/history-store` | W1 接口（可先 mock） | 可与 W1 并行 |
| W3 | `index.html + styles + ui/calculator-view + keyboard` | W1/W2 接口 | 可与 W1/W2 并行 |
| W4 | `ui/history-view + 移动端历史面板 + 可访问性` | W2/W3 | 是 |
| W5 | `test/*` 单元测试与人工验收清单执行 | W1/W2 | 测试可与实现同步 |
| W6 | 静态服务器/部署说明/README | W3 | 是 |

**集成检查点**

1. W1 单元测试全绿（含需求 §7 全表）。
2. W2 reducer 测试全绿（状态机表全表）。
3. W3 在 320px 与桌面双栏可用；键盘映射全通。
4. W4 历史持久化/降级/清空通过。
5. W5 安全扫描、CSP、读屏、设备矩阵通过。

---

*本文档与需求文档共同构成第一阶段交付。任何实现若偏离 §6、§7、§9 的显式约定，应先更新文档并评审；不得以「实现方便」为由静默改变语义。*
