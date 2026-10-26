import { test } from "node:test";
import assert from "node:assert/strict";

import { formatNumber } from "../src/core/formatter.js";

const CASES = [
  [0.30000000000000004, "0.3"],
  [1 / 3, "0.333333333333333"],
  [-0, "0"],
  [0, "0"],
  [1e16, "1e+16"],
  [1.5e16, "1.5e+16"],
  [1e-6, "0.000001"],
  [1e-7, "1e-7"],
  [123.45700000000001, "123.457"],
  [999999999999999, "999999999999999"],
  [-1.5e-7, "-1.5e-7"],
  [1e21, "1e+21"],
  [42, "42"],
  [-42.5, "-42.5"],
  [0.000001234, "0.000001234"],
];

for (const [value, expected] of CASES) {
  test(`formatter: ${String(value)} → ${expected}`, () => {
    assert.equal(formatNumber(value), expected);
  });
}

test("formatter: 15 位有效数字稳定化", () => {
  assert.equal(formatNumber(0.1 + 0.2), "0.3");
  assert.equal(formatNumber(1 / 3), "0.333333333333333");
  assert.equal(formatNumber(2 / 3), "0.666666666666667");
});

test("formatter: 非有限值不会输出 Infinity / NaN（防御性）", () => {
  assert.equal(formatNumber(Infinity), "0");
  assert.equal(formatNumber(-Infinity), "0");
  assert.equal(formatNumber(NaN), "0");
  assert.equal(formatNumber("12"), "0");
});

test("formatter: 不使用千分位与本地化分隔符", () => {
  const text = formatNumber(1234567.89);
  assert.equal(text, "1234567.89");
  assert.equal(text.includes(","), false);
});
