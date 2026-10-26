/**
 * 全局上限常量与检查函数（见 docs/architecture.md §7.3）。
 * 本模块无副作用、无 DOM 依赖。
 */

export const MAX_NUMBER_SIG_DIGITS = 15;
export const MAX_NUMBER_CHARS = 32;
export const MAX_EXPRESSION_CHARS = 128;
export const MAX_PAREN_DEPTH = 16;
export const MAX_HISTORY_ENTRIES = 50;
export const MAX_ID_LENGTH = 64;
export const MAX_HISTORY_EXPRESSION_CHARS = 128;
export const MAX_HISTORY_RESULT_CHARS = 32;

/**
 * 统计数字字面量的有效数字位数。
 * 规则：只取尾数部分（`e` 之前），去掉小数点与非数字，去掉前导 0；
 * 空串按 1 位计。例如 `0.0001` → 1，`1.000000000000000` → 16。
 *
 * @param {string} raw
 * @returns {number}
 */
export function countSignificantDigits(raw) {
  const mantissa = String(raw).split(/[eE]/)[0];
  const digits = mantissa.replace(/[^0-9]/g, "").replace(/^0+/, "");
  return digits.length === 0 ? 1 : digits.length;
}

/**
 * 数字字面量是否在字符长度与有效位上限内。
 *
 * @param {string} raw
 * @returns {boolean}
 */
export function isNumberWithinLimits(raw) {
  const text = String(raw);
  return (
    text.length <= MAX_NUMBER_CHARS &&
    countSignificantDigits(text) <= MAX_NUMBER_SIG_DIGITS
  );
}
