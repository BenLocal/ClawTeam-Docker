import { test } from "node:test";
import assert from "node:assert/strict";

import { createInitialState, reduce } from "../src/app/state.js";
import * as a from "../src/app/actions.js";
import { serialize } from "../src/core/serializer.js";
import { historyEntry } from "./helpers.js";

/** @param { import("../src/app/state.js").CalcState } state */
function run(state, ...actionList) {
  return actionList.reduce((current, action) => reduce(current, action), state);
}

/** @param { import("../src/app/state.js").CalcState } state */
function typeDigits(state, digits) {
  let current = state;
  for (const char of digits) {
    current = reduce(current, a.digit(char));
  }
  return current;
}

test("state: 初始状态为空态", () => {
  const state = createInitialState();
  assert.equal(state.phase, "empty");
  assert.deepEqual(state.tokens, []);
  assert.equal(state.result, null);
  assert.equal(state.error, null);
  assert.deepEqual(state.history, []);
  assert.equal(state.storageAvailable, true);
  assert.equal(state.notice, null);
});

test("state: 数字输入与前导零替换", () => {
  let state = reduce(createInitialState(), a.digit("0"));
  assert.equal(serialize(state.tokens), "0");
  state = reduce(state, a.digit("0"));
  assert.equal(serialize(state.tokens), "0");
  state = reduce(state, a.digit("7"));
  assert.equal(serialize(state.tokens), "7");
  assert.equal(state.phase, "editing");
});

test("state: 小数点规则（起始补 0.、唯一小数点）", () => {
  let state = reduce(createInitialState(), a.decimal());
  assert.equal(serialize(state.tokens), "0.");
  state = reduce(state, a.digit("5"));
  assert.equal(serialize(state.tokens), "0.5");
  state = reduce(state, a.decimal());
  assert.equal(serialize(state.tokens), "0.5");

  let afterOperator = run(createInitialState(), a.digit("2"), a.operator("+"), a.decimal());
  assert.equal(serialize(afterOperator.tokens), "2 + 0.");
});

test("state: 空态只能输入一元负号", () => {
  const empty = createInitialState();
  assert.equal(reduce(empty, a.operator("+")), empty);
  assert.equal(reduce(empty, a.operator("*")), empty);
  assert.equal(reduce(empty, a.percent()), empty);

  const negative = reduce(empty, a.operator("-"));
  assert.equal(negative.phase, "editing");
  assert.equal(serialize(negative.tokens), "−");
  assert.equal(serialize(typeDigits(negative, "5").tokens), "−5");
});

test("state: 二元运算符替换与一元负号叠加", () => {
  let state = run(createInitialState(), a.digit("2"), a.operator("+"), a.operator("*"));
  assert.equal(serialize(state.tokens), "2 ×");

  state = run(
    createInitialState(),
    a.digit("5"),
    a.operator("*"),
    a.operator("-"),
    a.digit("2"),
  );
  assert.equal(serialize(state.tokens), "5 × −2");
  assert.equal(reduce(state, a.evaluate()).resultText, "-10");

  state = run(createInitialState(), a.digit("2"), a.operator("-"), a.operator("-"), a.digit("3"));
  assert.equal(serialize(state.tokens), "2 − −3");
  assert.equal(reduce(state, a.evaluate()).resultText, "5");
});

test("state: 百分号输入（含连续百分号）", () => {
  let state = typeDigits(createInitialState(), "50");
  state = reduce(state, a.percent());
  state = reduce(state, a.percent());
  assert.equal(serialize(state.tokens), "50%%");
  assert.equal(state.previewText, "0.005");

  // `%` 可以继续叠加（设计 §6.2：可连续）。
  const third = reduce(state, a.percent());
  assert.equal(serialize(third.tokens), "50%%%");
  assert.equal(third.previewText, "0.00005");

  // 运算符或空态之后的 `%` 被忽略。
  const afterOperator = run(createInitialState(), a.digit("2"), a.operator("+"), a.percent());
  assert.equal(serialize(afterOperator.tokens), "2 +");
  assert.equal(reduce(createInitialState(), a.percent()).phase, "empty");
});

test("state: 括号与优先级", () => {
  let state = run(
    createInitialState(),
    a.paren("("),
    a.digit("1"),
    a.operator("+"),
    a.digit("2"),
    a.paren(")"),
    a.operator("*"),
    a.digit("3"),
  );
  assert.equal(serialize(state.tokens), "(1 + 2) × 3");
  assert.equal(state.previewText, "9");

  const evaluated = reduce(state, a.evaluate());
  assert.equal(evaluated.resultText, "9");
});

test("state: 非法括号被输入层忽略", () => {
  const empty = createInitialState();
  assert.equal(reduce(empty, a.paren(")")), empty);

  const two = reduce(createInitialState(), a.digit("2"));
  assert.equal(reduce(two, a.paren("(")), two);
});

test("state: 括号嵌套上限 16 层", () => {
  let state = createInitialState();
  for (let index = 0; index < 16; index += 1) {
    state = reduce(state, a.paren("("));
  }
  assert.equal(state.tokens.length, 16);

  const rejected = reduce(state, a.paren("("));
  assert.equal(rejected.tokens.length, 16);
  assert.equal(rejected.notice, "括号嵌套过深");
});

test("state: 15 位有效数字上限", () => {
  let state = typeDigits(createInitialState(), "123456789012345");
  assert.equal(serialize(state.tokens), "123456789012345");

  const rejected = reduce(state, a.digit("6"));
  assert.equal(serialize(rejected.tokens), "123456789012345");
  assert.equal(rejected.notice, "单个数字最多 15 位有效数字");
  assert.equal(rejected.phase, "editing");
});

test("state: 表达式长度上限 128", () => {
  let state = typeDigits(createInitialState(), "1");
  for (let index = 0; index < 50; index += 1) {
    state = reduce(state, a.operator("+"));
    state = reduce(state, a.digit("1"));
  }
  assert.equal(serialize(state.tokens).length <= 128, true);
  assert.equal(state.notice, "表达式过长");
});

test("state: 求值成功写入历史并进入 evaluated", () => {
  const state = run(
    createInitialState(),
    a.digit("0"),
    a.decimal(),
    a.digit("1"),
    a.operator("+"),
    a.digit("0"),
    a.decimal(),
    a.digit("2"),
    a.evaluate({ id: "entry-1", createdAt: "2026-10-26T10:00:00.000Z" }),
  );

  assert.equal(state.phase, "evaluated");
  assert.equal(state.resultText, "0.3");
  assert.equal(state.result, 0.30000000000000004);
  assert.equal(state.error, null);
  assert.equal(state.history.length, 1);
  assert.deepEqual(state.history[0], {
    id: "entry-1",
    expression: "0.1 + 0.2",
    result: "0.3",
    createdAt: "2026-10-26T10:00:00.000Z",
  });
});

test("state: 空态按 = 不产生历史", () => {
  const empty = createInitialState();
  assert.equal(reduce(empty, a.evaluate()), empty);
  assert.equal(empty.history.length, 0);
});

test("state: 不完整表达式按 = 进入错误态并保留表达式", () => {
  const state = run(createInitialState(), a.digit("2"), a.operator("+"));
  const failed = reduce(state, a.evaluate());
  assert.equal(failed.phase, "error");
  assert.equal(failed.error.code, "E_SYNTAX");
  assert.equal(serialize(failed.tokens), "2 +");
  assert.equal(failed.history.length, 0);
});

test("state: 除零与括号不匹配的错误态", () => {
  const divided = run(
    createInitialState(),
    a.digit("5"),
    a.operator("/"),
    a.digit("0"),
  );
  const dividedError = reduce(divided, a.evaluate());
  assert.equal(dividedError.phase, "error");
  assert.equal(dividedError.error.code, "E_DIV_ZERO");
  assert.equal(dividedError.error.message, "不能除以零");

  const unbalanced = run(
    createInitialState(),
    a.paren("("),
    a.digit("1"),
    a.operator("+"),
    a.digit("2"),
  );
  const unbalancedError = reduce(unbalanced, a.evaluate());
  assert.equal(unbalancedError.error.code, "E_UNBALANCED_PAREN");
});

test("state: 错误后数字 / AC / DEL 均可恢复", () => {
  const errorState = reduce(
    run(createInitialState(), a.digit("2"), a.operator("+")),
    a.evaluate(),
  );

  const byDigit = reduce(errorState, a.digit("3"));
  assert.equal(byDigit.phase, "editing");
  assert.equal(byDigit.error, null);
  assert.equal(serialize(byDigit.tokens), "3");

  const byClear = reduce(errorState, a.clearAll());
  assert.equal(byClear.phase, "empty");
  assert.deepEqual(byClear.tokens, []);

  const byDelete = reduce(errorState, a.deleteBack());
  assert.equal(byDelete.phase, "editing");
  assert.equal(byDelete.error, null);
  assert.equal(serialize(byDelete.tokens), "2");
});

test("state: 错误态忽略运算符 / 百分号 / =", () => {
  const errorState = reduce(
    run(createInitialState(), a.digit("2"), a.operator("+")),
    a.evaluate(),
  );
  assert.equal(reduce(errorState, a.operator("+")), errorState);
  assert.equal(reduce(errorState, a.percent()), errorState);
  assert.equal(reduce(errorState, a.evaluate()), errorState);
});

test("state: AC 清空表达式但保留历史与存储状态", () => {
  const state = run(
    createInitialState(),
    a.digit("2"),
    a.operator("+"),
    a.digit("3"),
    a.evaluate({ id: "1", createdAt: "2026-10-26T10:00:00.000Z" }),
  );
  const cleared = reduce(state, a.clearAll());
  assert.equal(cleared.phase, "empty");
  assert.deepEqual(cleared.tokens, []);
  assert.equal(cleared.resultText, null);
  assert.equal(cleared.history.length, 1);
});

test("state: DEL 按字符退格与按 token 删除", () => {
  let state = typeDigits(createInitialState(), "12");
  state = reduce(state, a.deleteBack());
  assert.equal(serialize(state.tokens), "1");
  state = reduce(state, a.deleteBack());
  assert.equal(state.phase, "empty");
  assert.deepEqual(state.tokens, []);
});

test("state: 求值后以结果继续计算", () => {
  const evaluated = run(
    createInitialState(),
    a.digit("2"),
    a.operator("+"),
    a.digit("3"),
    a.evaluate({ id: "a", createdAt: "2026-10-26T10:00:00.000Z" }),
  );

  const continued = run(evaluated, a.operator("*"), a.digit("2"));
  assert.equal(serialize(continued.tokens), "5 × 2");
  const final = reduce(continued, a.evaluate({ id: "b" }));
  assert.equal(final.resultText, "10");
  assert.equal(final.history.length, 2);
  assert.equal(final.history[0].expression, "5 × 2");
});

test("state: 求值后数字 / 括号开始新表达式", () => {
  const evaluated = run(
    createInitialState(),
    a.digit("2"),
    a.operator("+"),
    a.digit("3"),
    a.evaluate({ id: "a", createdAt: "2026-10-26T10:00:00.000Z" }),
  );

  const newDigit = reduce(evaluated, a.digit("7"));
  assert.equal(newDigit.phase, "editing");
  assert.equal(serialize(newDigit.tokens), "7");

  const newParen = reduce(evaluated, a.paren("("));
  assert.equal(serialize(newParen.tokens), "(");
});

test("state: 求值后 % 以结果为操作数继续", () => {
  const evaluated = run(
    createInitialState(),
    a.digit("2"),
    a.operator("+"),
    a.digit("3"),
    a.evaluate({ id: "a", createdAt: "2026-10-26T10:00:00.000Z" }),
  );
  const percentState = reduce(evaluated, a.percent());
  assert.equal(percentState.phase, "editing");
  assert.equal(serialize(percentState.tokens), "5%");
  assert.equal(percentState.previewText, "0.05");
});

test("state: 求值后按 = 不重复运算", () => {
  const evaluated = run(
    createInitialState(),
    a.digit("2"),
    a.operator("+"),
    a.digit("3"),
    a.evaluate({ id: "a", createdAt: "2026-10-26T10:00:00.000Z" }),
  );
  assert.equal(reduce(evaluated, a.evaluate()), evaluated);
  assert.equal(evaluated.history.length, 1);
});

test("state: 求值后 DEL 回到编辑态并删除记号", () => {
  const evaluated = run(
    createInitialState(),
    a.digit("2"),
    a.operator("+"),
    a.digit("3"),
    a.evaluate({ id: "a", createdAt: "2026-10-26T10:00:00.000Z" }),
  );
  const edited = reduce(evaluated, a.deleteBack());
  assert.equal(edited.phase, "editing");
  assert.equal(edited.resultText, null);
  assert.equal(serialize(edited.tokens), "2 +");
});

test("state: ± 切换当前操作数（数字 / 括号 / 百分号）", () => {
  let state = reduce(createInitialState(), a.digit("3"));
  state = reduce(state, a.toggleSign());
  assert.equal(serialize(state.tokens), "−3");
  state = reduce(state, a.toggleSign());
  assert.equal(serialize(state.tokens), "3");

  let group = run(
    createInitialState(),
    a.paren("("),
    a.digit("2"),
    a.operator("+"),
    a.digit("3"),
    a.paren(")"),
  );
  group = reduce(group, a.toggleSign());
  assert.equal(serialize(group.tokens), "−(2 + 3)");
  assert.equal(reduce(group, a.evaluate()).resultText, "-5");

  let negativeOperand = run(
    createInitialState(),
    a.digit("2"),
    a.operator("-"),
    a.digit("3"),
  );
  negativeOperand = reduce(negativeOperand, a.toggleSign());
  // 设计 §6.3：± 在操作数前插入一元负号，不额外加括号。
  assert.equal(serialize(negativeOperand.tokens), "2 − −3");
  assert.equal(reduce(negativeOperand, a.evaluate()).resultText, "5");
  negativeOperand = reduce(negativeOperand, a.toggleSign());
  assert.equal(serialize(negativeOperand.tokens), "2 − 3");

  let percentState = run(
    createInitialState(),
    a.operator("-"),
    a.digit("3"),
    a.percent(),
  );
  percentState = reduce(percentState, a.toggleSign());
  assert.equal(serialize(percentState.tokens), "3%");
});

test("state: 求值后 ± 对结果取反并进入编辑态", () => {
  const evaluated = run(
    createInitialState(),
    a.digit("2"),
    a.operator("+"),
    a.digit("3"),
    a.evaluate({ id: "a", createdAt: "2026-10-26T10:00:00.000Z" }),
  );
  const toggled = reduce(evaluated, a.toggleSign());
  assert.equal(toggled.phase, "editing");
  assert.equal(serialize(toggled.tokens), "−5");
  assert.equal(toggled.previewText, "-5");
});

test("state: 空态 ± 插入一元负号", () => {
  const state = reduce(createInitialState(), a.toggleSign());
  assert.equal(serialize(state.tokens), "−");
});

test("state: 历史去重（表达式与结果相同只刷新时间）", () => {
  let state = run(
    createInitialState(),
    a.digit("2"),
    a.operator("+"),
    a.digit("3"),
    a.evaluate({ id: "first", createdAt: "2026-10-26T10:00:00.000Z" }),
  );
  state = reduce(state, a.clearAll());
  state = run(
    state,
    a.digit("2"),
    a.operator("+"),
    a.digit("3"),
    a.evaluate({ id: "second", createdAt: "2026-10-26T11:00:00.000Z" }),
  );

  assert.equal(state.history.length, 1);
  assert.equal(state.history[0].id, "first");
  assert.equal(state.history[0].createdAt, "2026-10-26T11:00:00.000Z");
});

test("state: 历史上限 50 条，最新在前", () => {
  const existing = Array.from({ length: 50 }, (_, index) =>
    historyEntry(`old-${index}`, `0 + ${index}`, String(index)),
  );
  let state = createInitialState(existing);
  state = run(
    state,
    a.digit("1"),
    a.operator("+"),
    a.digit("1"),
    a.evaluate({ id: "new", createdAt: "2026-10-26T12:00:00.000Z" }),
  );

  assert.equal(state.history.length, 50);
  assert.equal(state.history[0].expression, "1 + 1");
  assert.equal(state.history[0].id, "new");
  assert.equal(state.history[49].expression, "0 + 48");
});

test("state: loadHistory 载入表达式但不自动求值", () => {
  const entry = historyEntry("h1", "3 + 4 × 2", "11");
  const state = createInitialState([entry]);
  const loaded = reduce(state, a.loadHistory("h1"));

  assert.equal(loaded.phase, "editing");
  assert.equal(serialize(loaded.tokens), "3 + 4 × 2");
  assert.equal(loaded.previewText, "11");
  assert.equal(loaded.result, null);
  assert.equal(loaded.error, null);
});

test("state: loadHistory 对未知 id 或无法解析的表达式保持不变", () => {
  const state = createInitialState([historyEntry("h1", "1.2.3", "0")]);
  assert.equal(reduce(state, a.loadHistory("missing")), state);
  assert.equal(reduce(state, a.loadHistory("h1")), state);
});

test("state: clearHistory 清空历史，其余状态不变", () => {
  const state = createInitialState([historyEntry("h1", "3 + 4", "7")]);
  const cleared = reduce(state, a.clearHistory());
  assert.deepEqual(cleared.history, []);
  assert.equal(cleared.phase, state.phase);

  const empty = createInitialState();
  assert.equal(reduce(empty, a.clearHistory()), empty);
});

test("state: hydrateHistory 与 storageAvailable", () => {
  const entries = [historyEntry("h1", "1 + 1", "2")];
  const state = reduce(createInitialState(), a.hydrateHistory(entries));
  assert.deepEqual(state.history, entries);

  const nonArray = reduce(state, a.hydrateHistory("nope"));
  assert.equal(nonArray, state);

  const unavailable = reduce(state, a.setStorageAvailable(false));
  assert.equal(unavailable.storageAvailable, false);

  const many = Array.from({ length: 60 }, (_, index) =>
    historyEntry(`h-${index}`, `1 + ${index}`, String(index + 1)),
  );
  const truncated = reduce(state, a.hydrateHistory(many));
  assert.equal(truncated.history.length, 50);
});

test("state: 输入层阻止隐式乘法组合", () => {
  const two = reduce(createInitialState(), a.digit("2"));
  assert.equal(reduce(two, a.paren("(")), two);

  const percentState = run(createInitialState(), a.digit("2"), a.percent());
  assert.equal(reduce(percentState, a.digit("3")), percentState);
  assert.equal(reduce(percentState, a.paren("(")), percentState);

  const closedGroup = run(
    createInitialState(),
    a.paren("("),
    a.digit("2"),
    a.paren(")"),
  );
  assert.equal(reduce(closedGroup, a.digit("3")), closedGroup);
});

test("state: 未知动作不改变状态", () => {
  const state = createInitialState();
  assert.equal(reduce(state, { type: "unknown" }), state);
  assert.equal(reduce(state, null), state);
});
