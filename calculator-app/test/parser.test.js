import { test } from "node:test";
import assert from "node:assert/strict";

import { tokenize } from "../src/core/tokenizer.js";
import { parse } from "../src/core/parser.js";

/** @param {string} expression */
function parseExpression(expression) {
  const tokenized = tokenize(expression);
  assert.equal(tokenized.ok, true, `tokenize failed: ${expression}`);
  return parse(tokenized.tokens);
}

test("parser: 3 + 4 × 2 的乘法优先", () => {
  const result = parseExpression("3 + 4 × 2");
  assert.equal(result.ok, true);
  assert.equal(result.ast.type, "binary");
  assert.equal(result.ast.op, "+");
  assert.equal(result.ast.right.type, "binary");
  assert.equal(result.ast.right.op, "*");
});

test("parser: 2 − 3 − 4 左结合", () => {
  const result = parseExpression("2 − 3 − 4");
  assert.equal(result.ok, true);
  assert.equal(result.ast.op, "-");
  assert.equal(result.ast.left.type, "binary");
  assert.equal(result.ast.left.op, "-");
  assert.equal(result.ast.right.type, "num");
});

test("parser: 括号改变结合结构", () => {
  const result = parseExpression("(1 + 2) × 3");
  assert.equal(result.ok, true);
  assert.equal(result.ast.op, "*");
  assert.equal(result.ast.left.type, "binary");
  assert.equal(result.ast.left.op, "+");
});

test("parser: 一元负号包裹百分号 → -3% = -(3%)", () => {
  const result = parseExpression("−3%");
  assert.equal(result.ok, true);
  assert.equal(result.ast.type, "unary");
  assert.equal(result.ast.op, "-");
  assert.equal(result.ast.operand.type, "percent");
  assert.equal(result.ast.operand.operand.type, "num");
});

test("parser: 连续一元负号右结合", () => {
  const result = parseExpression("−−3");
  assert.equal(result.ok, true);
  assert.equal(result.ast.type, "unary");
  assert.equal(result.ast.operand.type, "unary");
  assert.equal(result.ast.operand.operand.type, "num");
});

test("parser: 16 层括号允许，17 层返回 E_TOO_DEEP", () => {
  const allowed = parseExpression(`${"(".repeat(16)}1${")".repeat(16)}`);
  assert.equal(allowed.ok, true);

  const rejected = parseExpression(`${"(".repeat(17)}1${")".repeat(17)}`);
  assert.equal(rejected.ok, false);
  assert.equal(rejected.error.code, "E_TOO_DEEP");
});

test("parser: 隐式乘法（2(3+4)、相邻数字、%后数字）返回 E_IMPLICIT_MUL", () => {
  for (const expression of ["2(3 + 4)", "(1 + 2)(3 + 4)", "2 3", "2%3", "(2)3"]) {
    const result = parseExpression(expression);
    assert.equal(result.ok, false, expression);
    assert.equal(result.error.code, "E_IMPLICIT_MUL", expression);
  }
});

test("parser: 空输入与不完整表达式返回 E_SYNTAX", () => {
  assert.equal(parse([]).ok, false);
  assert.equal(parse([]).error.code, "E_SYNTAX");

  for (const expression of ["2 +", "*3", "%", "1 + * 2"]) {
    const result = parseExpression(expression);
    assert.equal(result.ok, false, expression);
    assert.equal(result.error.code, "E_SYNTAX", expression);
  }
});

test("parser: 括号不匹配返回 E_UNBALANCED_PAREN", () => {
  for (const expression of ["(1 + 2", "1 + 2)", ")", "()"]) {
    const result = parseExpression(expression);
    assert.equal(result.ok, false, expression);
    assert.equal(result.error.code, "E_UNBALANCED_PAREN", expression);
  }
});

test("parser: 数字字面量溢出返回 E_OVERFLOW", () => {
  const result = parseExpression("1e999");
  assert.equal(result.ok, false);
  assert.equal(result.error.code, "E_OVERFLOW");
});

test("parser: 错误对象包含用户文案与位置", () => {
  const result = parseExpression("2(3)");
  assert.equal(result.ok, false);
  assert.equal(result.error.message, "不支持省略乘号，请使用 ×");
  assert.equal(typeof result.error.position, "number");
});

test("parser: 非数组输入不抛异常", () => {
  const result = parse(null);
  assert.equal(result.ok, false);
  assert.equal(result.error.code, "E_SYNTAX");
});
