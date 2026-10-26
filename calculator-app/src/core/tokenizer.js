/**
 * 词法分析：字符流 → Token[]（architecture.md §5.1）。只做词法校验，不访问 DOM。
 */

import { fail } from "./errors.js";
import { MAX_EXPRESSION_CHARS, isNumberWithinLimits } from "./limits.js";

/**
 * @typedef {{type:"num", raw:string, start:number, end:number}
 *   | {type:"op", value:"+"|"-"|"*"|"/", start:number, end:number}
 *   | {type:"lparen"|"rparen"|"percent", start:number, end:number}} Token
 */

/** 显示符号 → 内部 ASCII。 */
const DISPLAY_SYMBOLS = new Map([
  ["×", "*"],
  ["÷", "/"],
  ["−", "-"],
]);

/** @param {string} ch */
function isDigit(ch) {
  return ch >= "0" && ch <= "9";
}

/** @param {string} ch */
function isWhitespace(ch) {
  return ch === " " || ch === "\t" || ch === "\n" || ch === "\r";
}

/**
 * @param {string} input
 * @returns {{ok: true, tokens: Token[]} | {ok: false, error: import("./errors.js").CalcError}}
 */
export function tokenize(input) {
  if (typeof input !== "string") {
    return fail("E_SYNTAX", { detail: "input must be a string" });
  }
  if (input.length > MAX_EXPRESSION_CHARS) {
    return fail("E_TOO_LONG");
  }

  /** @type {Token[]} */
  const tokens = [];
  let index = 0;

  while (index < input.length) {
    const char = input[index];
    if (isWhitespace(char)) {
      index += 1;
      continue;
    }

    const normalized = DISPLAY_SYMBOLS.get(char) ?? char;
    const start = index;

    if (isDigit(char) || char === ".") {
      let cursor = index;
      let sawDigit = false;

      while (cursor < input.length && isDigit(input[cursor])) {
        cursor += 1;
        sawDigit = true;
      }
      if (input[cursor] === ".") {
        cursor += 1;
        while (cursor < input.length && isDigit(input[cursor])) {
          cursor += 1;
          sawDigit = true;
        }
      }
      if (!sawDigit) {
        return fail("E_SYNTAX", { position: start });
      }
      if (input[cursor] === ".") {
        // 1.2.3：数字后紧跟第二个小数点。
        return fail("E_SYNTAX", { position: cursor });
      }
      if (input[cursor] === "e" || input[cursor] === "E") {
        const exponentStart = cursor;
        let exponentCursor = cursor + 1;
        if (input[exponentCursor] === "+" || input[exponentCursor] === "-") {
          exponentCursor += 1;
        }
        const exponentDigitsStart = exponentCursor;
        while (exponentCursor < input.length && isDigit(input[exponentCursor])) {
          exponentCursor += 1;
        }
        if (exponentCursor === exponentDigitsStart) {
          return fail("E_SYNTAX", { position: exponentStart });
        }
        cursor = exponentCursor;
      }

      let raw = input.slice(start, cursor);
      if (!isNumberWithinLimits(raw)) {
        return fail("E_NUMBER_TOO_LONG", { position: start });
      }
      if (raw.startsWith(".")) {
        raw = `0${raw}`;
      }
      tokens.push({ type: "num", raw, start, end: cursor });
      index = cursor;
      continue;
    }

    if (
      normalized === "+" ||
      normalized === "-" ||
      normalized === "*" ||
      normalized === "/"
    ) {
      tokens.push({
        type: "op",
        value: /** @type {"+"|"-"|"*"|"/"} */ (normalized),
        start,
        end: start + 1,
      });
      index += 1;
      continue;
    }

    if (normalized === "(" || normalized === ")" || normalized === "%") {
      const type =
        normalized === "(" ? "lparen" : normalized === ")" ? "rparen" : "percent";
      tokens.push({ type, start, end: start + 1 });
      index += 1;
      continue;
    }

    return fail("E_SYNTAX", {
      position: start,
      detail: `unknown character: ${char}`,
    });
  }

  return { ok: true, tokens };
}
