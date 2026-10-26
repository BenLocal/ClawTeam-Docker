import { test } from "node:test";
import assert from "node:assert/strict";

import { evaluate } from "../src/core/evaluator.js";
import { calc } from "./helpers.js";

const PRIORITY_CASES = [
  ["3 + 4 × 2", "11"],
  ["12 ÷ 3 × 2", "8"],
  ["2 − 3 − 4", "-5"],
  ["(1 + 2) × 3", "9"],
  ["2 × (3 + 4)", "14"],
  ["1 ÷ 3", "0.333333333333333"],
  ["0.1 + 0.2", "0.3"],
];

for (const [expression, expected] of PRIORITY_CASES) {
  test(`evaluator: ${expression} = ${expected}`, () => {
    const result = calc(expression);
    assert.equal(result.ok, true);
    assert.equal(result.text, expected);
  });
}

const PERCENT_CASES = [
  ["50 + 10%", "50.1"],
  ["50 − 10%", "49.9"],
  ["50 × 10%", "5"],
  ["50 ÷ 10%", "500"],
  ["(50 + 50)%", "1"],
  ["50%%", "0.005"],
  ["−3%", "-0.03"],
];

for (const [expression, expected] of PERCENT_CASES) {
  test(`evaluator 百分号: ${expression} = ${expected}`, () => {
    const result = calc(expression);
    assert.equal(result.ok, true);
    assert.equal(result.text, expected);
  });
}

const UNARY_CASES = [
  ["−2 × 3", "-6"],
  ["5 × −2", "-10"],
  ["2 − −3", "5"],
  ["− − 3", "3"],
  ["−(2 + 3)", "-5"],
  ["−(−3)", "3"],
  ["−−3", "3"],
  ["+(2 + 3)", "5"],
];

for (const [expression, expected] of UNARY_CASES) {
  test(`evaluator 一元负号: ${expression} = ${expected}`, () => {
    const result = calc(expression);
    assert.equal(result.ok, true);
    assert.equal(result.text, expected);
  });
}

test("evaluator: 除以零（含 -0、0÷0、百分号零）返回 E_DIV_ZERO", () => {
  for (const expression of ["5 ÷ 0", "0 ÷ 0", "5 ÷ -0", "5 ÷ 0%", "5 ÷ (2 − 2)"]) {
    const result = calc(expression);
    assert.equal(result.ok, false, expression);
    assert.equal(result.error.code, "E_DIV_ZERO", expression);
    assert.equal(result.error.message, "不能除以零");
  }
});

test("evaluator: 运算溢出返回 E_OVERFLOW", () => {
  for (const expression of ["1e308 × 10", "1e999", "−1e999"]) {
    const result = calc(expression);
    assert.equal(result.ok, false, expression);
    assert.equal(result.error.code, "E_OVERFLOW", expression);
  }
});

test("evaluator: 下溢为 0 不报错", () => {
  const result = calc("1e-300 × 1e-300");
  assert.equal(result.ok, true);
  assert.equal(result.value, 0);
  assert.equal(result.text, "0");
});

test("evaluator: 负零结果被保留为 -0，格式化后显示 0", () => {
  const negativeZero = calc("0 × −1");
  assert.equal(negativeZero.ok, true);
  assert.equal(Object.is(negativeZero.value, -0), true);
  assert.equal(negativeZero.text, "0");

  const directZero = calc("−0");
  assert.equal(directZero.ok, true);
  assert.equal(Object.is(directZero.value, -0), true);
  assert.equal(directZero.text, "0");
});

test("evaluator: 防御性处理 null / 未知 AST", () => {
  assert.equal(evaluate(null).ok, false);
  assert.equal(evaluate(null).error.code, "E_UNKNOWN");

  const unknown = evaluate({ type: "wat" });
  assert.equal(unknown.ok, false);
  assert.equal(unknown.error.code, "E_UNKNOWN");
});

test("evaluator: 非有限字面量不返回 Infinity", () => {
  const result = evaluate({ type: "num", raw: "Infinity" });
  assert.equal(result.ok, false);
  assert.equal(result.error.code, "E_OVERFLOW");
});
