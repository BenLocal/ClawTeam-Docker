import { test } from "node:test";
import assert from "node:assert/strict";

import { tokenize } from "../src/core/tokenizer.js";

test("tokenize: 数字、小数与位置信息", () => {
  const result = tokenize("12.5");
  assert.equal(result.ok, true);
  assert.equal(result.tokens.length, 1);
  assert.deepEqual(
    { type: result.tokens[0].type, raw: result.tokens[0].raw },
    { type: "num", raw: "12.5" },
  );
  assert.equal(result.tokens[0].start, 0);
  assert.equal(result.tokens[0].end, 4);
});

test("tokenize: .5 规范化为 0.5，5. 保留原样", () => {
  const leading = tokenize(".5");
  assert.equal(leading.ok, true);
  assert.equal(leading.tokens[0].raw, "0.5");

  const trailing = tokenize("5.");
  assert.equal(trailing.ok, true);
  assert.equal(trailing.tokens[0].raw, "5.");
});

test("tokenize: 科学计数法 1.5e+16 / 1e-7", () => {
  const positive = tokenize("1.5e+16");
  assert.equal(positive.ok, true);
  assert.equal(positive.tokens[0].raw, "1.5e+16");

  const negative = tokenize("1e-7");
  assert.equal(negative.ok, true);
  assert.equal(negative.tokens[0].raw, "1e-7");
});

test("tokenize: 显示符号 × ÷ − 归一化为 ASCII 运算符", () => {
  const result = tokenize("2×3÷4−5");
  assert.equal(result.ok, true);
  assert.deepEqual(
    result.tokens.map((token) => (token.type === "op" ? token.value : token.type)),
    ["num", "*", "num", "/", "num", "-", "num"],
  );
});

test("tokenize: 忽略空白", () => {
  const result = tokenize(" 3 + 4\t");
  assert.equal(result.ok, true);
  assert.equal(result.tokens.length, 3);
  assert.deepEqual(
    result.tokens.map((token) => (token.type === "op" ? token.value : token.type)),
    ["num", "+", "num"],
  );
});

test("tokenize: 括号与百分号 token", () => {
  const result = tokenize("(50 + 50)%");
  assert.equal(result.ok, true);
  assert.deepEqual(
    result.tokens.map((token) => token.type),
    ["lparen", "num", "op", "num", "rparen", "percent"],
  );
});

test("tokenize: 未知字符返回 E_SYNTAX 且带位置", () => {
  const result = tokenize("3 ^ 2");
  assert.equal(result.ok, false);
  assert.equal(result.error.code, "E_SYNTAX");
  assert.equal(result.error.position, 2);
});

test("tokenize: 1.2.3 返回语法错误", () => {
  const result = tokenize("1.2.3");
  assert.equal(result.ok, false);
  assert.equal(result.error.code, "E_SYNTAX");
});

test("tokenize: 1e / . 返回语法错误", () => {
  assert.equal(tokenize("1e").ok, false);
  assert.equal(tokenize(".").ok, false);
});

test("tokenize: 15 位有效数字允许，16 位拒绝", () => {
  assert.equal(tokenize("123456789012345").ok, true);
  const result = tokenize("1234567890123456");
  assert.equal(result.ok, false);
  assert.equal(result.error.code, "E_NUMBER_TOO_LONG");
});

test("tokenize: 单个数字超过 32 字符拒绝", () => {
  const result = tokenize(`0.${"0".repeat(30)}1`);
  assert.equal(result.ok, false);
  assert.equal(result.error.code, "E_NUMBER_TOO_LONG");
});

test("tokenize: 表达式超过 128 字符返回 E_TOO_LONG", () => {
  const result = tokenize("1+".repeat(70));
  assert.equal(result.ok, false);
  assert.equal(result.error.code, "E_TOO_LONG");
});

test("tokenize: 非字符串输入不抛异常", () => {
  const result = tokenize(42);
  assert.equal(result.ok, false);
  assert.equal(result.error.code, "E_SYNTAX");
});
