/**
 * 错误码、用户文案与错误对象工厂（见 docs/architecture.md §7.1、§7.2）。
 * 所有核心模块返回 `{ok:false, error}`，不向调用方抛异常。
 */

/** @typedef {{code: string, message: string, position?: number, detail?: string}} CalcError */

export const ERROR_MESSAGES = Object.freeze({
  E_SYNTAX: "表达式不完整或有误",
  E_UNBALANCED_PAREN: "括号不匹配",
  E_IMPLICIT_MUL: "不支持省略乘号，请使用 ×",
  E_DIV_ZERO: "不能除以零",
  E_OVERFLOW: "结果超出可表示范围",
  E_TOO_LONG: "表达式过长",
  E_TOO_DEEP: "括号嵌套过深",
  E_NUMBER_TOO_LONG: "单个数字最多 15 位有效数字",
  E_UNKNOWN: "无法计算，请检查输入",
});

/**
 * @param {string} code
 * @param {{position?: number, detail?: string}} [options]
 * @returns {CalcError}
 */
export function createError(code, options = {}) {
  const message = ERROR_MESSAGES[code] ?? ERROR_MESSAGES.E_UNKNOWN;
  /** @type {CalcError} */
  const error = { code, message };
  if (Number.isInteger(options.position)) {
    error.position = options.position;
  }
  if (typeof options.detail === "string" && options.detail.length > 0) {
    error.detail = options.detail;
  }
  return error;
}

/**
 * 构造失败结果。
 *
 * @param {string} code
 * @param {{position?: number, detail?: string}} [options]
 * @returns {{ok: false, error: CalcError}}
 */
export function fail(code, options) {
  return { ok: false, error: createError(code, options) };
}
