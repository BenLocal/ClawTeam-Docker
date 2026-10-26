import { test } from "node:test";
import assert from "node:assert/strict";

import {
  MAX_EXPRESSION_CHARS,
  MAX_HISTORY_ENTRIES,
  MAX_NUMBER_CHARS,
  MAX_NUMBER_SIG_DIGITS,
  MAX_PAREN_DEPTH,
  countSignificantDigits,
  isNumberWithinLimits,
} from "../src/core/limits.js";

test("limits: 常量与架构文档一致", () => {
  assert.equal(MAX_NUMBER_SIG_DIGITS, 15);
  assert.equal(MAX_NUMBER_CHARS, 32);
  assert.equal(MAX_EXPRESSION_CHARS, 128);
  assert.equal(MAX_PAREN_DEPTH, 16);
  assert.equal(MAX_HISTORY_ENTRIES, 50);
});

test("limits: 有效数字计数去掉小数点、非数字与前导 0", () => {
  assert.equal(countSignificantDigits("0.0001"), 1);
  assert.equal(countSignificantDigits("1000000000000000"), 16);
  assert.equal(countSignificantDigits("1.000000000000000"), 16);
  assert.equal(countSignificantDigits("000123"), 3);
  assert.equal(countSignificantDigits("0"), 1);
  assert.equal(countSignificantDigits(""), 1);
  assert.equal(countSignificantDigits(".5"), 1);
  assert.equal(countSignificantDigits("12.50"), 4);
});

test("limits: 科学计数只统计尾数有效位", () => {
  assert.equal(countSignificantDigits("1e+16"), 1);
  assert.equal(countSignificantDigits("1.5e-7"), 2);
  assert.equal(countSignificantDigits("1.000000000000000e5"), 16);
});

test("limits: 数字字面量上限判断", () => {
  assert.equal(isNumberWithinLimits("123456789012345"), true);
  assert.equal(isNumberWithinLimits("1234567890123456"), false);
  assert.equal(isNumberWithinLimits(`0.${"0".repeat(30)}1`), false);
});
