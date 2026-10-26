import { test } from "node:test";
import assert from "node:assert/strict";

import { tokenize } from "../src/core/tokenizer.js";
import { serialize } from "../src/core/serializer.js";
import { tokenShape } from "./helpers.js";

/** @param {string} expression */
function serialized(expression) {
  const result = tokenize(expression);
  assert.equal(result.ok, true, `tokenize failed: ${expression}`);
  return serialize(result.tokens);
}

test("serializer: 二元运算符两侧加空格，显示 × ÷ −", () => {
  assert.equal(serialized("3+4*2"), "3 + 4 × 2");
  assert.equal(serialized("12/3*2"), "12 ÷ 3 × 2");
  assert.equal(serialized("2-3-4"), "2 − 3 − 4");
});

test("serializer: 一元负号紧贴操作数", () => {
  assert.equal(serialized("-3%"), "−3%");
  assert.equal(serialized("-(2+3)"), "−(2 + 3)");
  assert.equal(serialized("2-(-3)"), "2 − (−3)");
  assert.equal(serialized("5*-2"), "5 × −2");
});

test("serializer: 括号与百分号", () => {
  assert.equal(serialized("(1+2)*3"), "(1 + 2) × 3");
  assert.equal(serialized("(50+50)%"), "(50 + 50)%");
  assert.equal(serialized("50%%"), "50%%");
});

test("serializer: 科学计数与小数原样保留", () => {
  assert.equal(serialized("1e+16"), "1e+16");
  assert.equal(serialized("0.5"), "0.5");
});

const ROUND_TRIP = [
  "3 + 4 × 2",
  "−(2 + 3)",
  "5 × −2",
  "50%%",
  "(1 + 2) × 3",
  "2 − (−3)",
  "1e+16",
  "0.5",
  "((1))",
  "2 − −3",
];

for (const expression of ROUND_TRIP) {
  test(`serializer round-trip: ${expression}`, () => {
    const first = tokenize(expression);
    assert.equal(first.ok, true);

    const text = serialize(first.tokens);
    const second = tokenize(text);
    assert.equal(second.ok, true, `re-tokenize failed: ${text}`);
    assert.deepEqual(tokenShape(second.tokens), tokenShape(first.tokens));
  });
}
