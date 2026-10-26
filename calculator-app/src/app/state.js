/** 初始状态与纯 reducer（architecture.md §8）；不访问 DOM/存储，不抛异常。 */

import { serialize, isBinaryOpAt, isOperandEnd } from "../core/serializer.js";
import { parse } from "../core/parser.js";
import { evaluate } from "../core/evaluator.js";
import { formatNumber } from "../core/formatter.js";
import { tokenize } from "../core/tokenizer.js";
import { ERROR_MESSAGES } from "../core/errors.js";
import {
  MAX_EXPRESSION_CHARS,
  MAX_HISTORY_ENTRIES,
  MAX_NUMBER_CHARS,
  MAX_NUMBER_SIG_DIGITS,
  MAX_PAREN_DEPTH,
  countSignificantDigits,
} from "../core/limits.js";
import { ACTIONS } from "./actions.js";

/**
 * @typedef {"empty"|"editing"|"evaluated"|"error"} Phase
 * @typedef {{id:string, expression:string, result:string, createdAt:string}} HistoryEntry
 * @typedef {Object} CalcState
 * @property {Phase} phase
 * @property {import("../core/tokenizer.js").Token[]} tokens
 * @property {number|null} result
 * @property {string|null} resultText
 * @property {string|null} previewText
 * @property {import("../core/errors.js").CalcError|null} error
 * @property {HistoryEntry[]} history
 * @property {boolean} storageAvailable
 * @property {string|null} notice 超限输入的一次性提示
 */

/** @param {HistoryEntry[]} [history] @returns {CalcState} */
export function createInitialState(history = []) {
  return {
    phase: "empty",
    tokens: [],
    result: null,
    resultText: null,
    previewText: null,
    error: null,
    history: Array.isArray(history)
      ? history.slice(0, MAX_HISTORY_ENTRIES)
      : [],
    storageAvailable: true,
    notice: null,
  };
}

/** @param {CalcState} state @param {string} message */
function withNotice(state, message) {
  return { ...state, notice: message };
}

/** 静默预览：任何失败都返回 null。 @param {import("../core/tokenizer.js").Token[]} tokens */
function computePreview(tokens) {
  try {
    const parsed = parse(tokens);
    if (!parsed.ok) {
      return null;
    }
    const evaluated = evaluate(parsed.ast);
    return evaluated.ok ? formatNumber(evaluated.value) : null;
  } catch {
    return null;
  }
}

/** 用 token 列表结束一次编辑，集中处理上限、预览与状态字段。 */
function finalizeEdit(state, tokens) {
  if (tokens.length === 0) {
    return {
      ...state,
      phase: "empty",
      tokens: [],
      result: null,
      resultText: null,
      previewText: null,
      error: null,
      notice: null,
    };
  }

  let text;
  try {
    text = serialize(tokens);
  } catch {
    return withNotice(state, ERROR_MESSAGES.E_SYNTAX);
  }
  if (text.length > MAX_EXPRESSION_CHARS) {
    return withNotice(state, ERROR_MESSAGES.E_TOO_LONG);
  }

  return {
    ...state,
    phase: "editing",
    tokens,
    result: null,
    resultText: null,
    previewText: computePreview(tokens),
    error: null,
    notice: null,
  };
}

/** @param {string} raw @returns {string|null} */
function numberLimitNotice(raw) {
  if (
    raw.length > MAX_NUMBER_CHARS ||
    countSignificantDigits(raw) > MAX_NUMBER_SIG_DIGITS
  ) {
    return ERROR_MESSAGES.E_NUMBER_TOO_LONG;
  }
  return null;
}

function generateId() {
  try {
    if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
      return globalThis.crypto.randomUUID();
    }
  } catch {
    // 降级到时间戳 + 随机串。
  }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
}

/** 最新在前、相同表达式+结果只刷新时间、上限 50。 */
function appendHistory(history, entry) {
  if (
    history.length > 0 &&
    history[0].expression === entry.expression &&
    history[0].result === entry.result
  ) {
    return [{ ...history[0], createdAt: entry.createdAt }, ...history.slice(1)];
  }
  return [entry, ...history].slice(0, MAX_HISTORY_ENTRIES);
}

/** @param {import("../core/tokenizer.js").Token[]} tokens */
function openParenDepth(tokens) {
  let depth = 0;
  for (const token of tokens) {
    if (token.type === "lparen") {
      depth += 1;
    } else if (token.type === "rparen") {
      depth -= 1;
    }
  }
  return depth;
}

/** @param {CalcState} state @param {{type: string} & Record<string, any>} action */
export function reduce(state, action) {
  if (!action || typeof action.type !== "string") {
    return state;
  }

  switch (action.type) {
    case ACTIONS.DIGIT:
      return reduceDigit(state, action.value);
    case ACTIONS.DECIMAL:
      return reduceDecimal(state);
    case ACTIONS.OPERATOR:
      return reduceOperator(state, action.value);
    case ACTIONS.PERCENT:
      return reducePercent(state);
    case ACTIONS.PAREN:
      return reduceParen(state, action.value);
    case ACTIONS.TOGGLE_SIGN:
      return reduceToggleSign(state);
    case ACTIONS.EVALUATE:
      return reduceEvaluate(state, action);
    case ACTIONS.CLEAR_ALL:
      return clearExpression(state);
    case ACTIONS.DELETE_BACK:
      return reduceDeleteBack(state);
    case ACTIONS.LOAD_HISTORY:
      return reduceLoadHistory(state, action.id);
    case ACTIONS.CLEAR_HISTORY:
      return state.history.length === 0 ? state : { ...state, history: [] };
    case ACTIONS.HYDRATE_HISTORY:
      return Array.isArray(action.entries)
        ? { ...state, history: action.entries.slice(0, MAX_HISTORY_ENTRIES) }
        : state;
    case ACTIONS.SET_STORAGE_AVAILABLE:
      return { ...state, storageAvailable: Boolean(action.value) };
    default:
      return state;
  }
}

/** AC：清空表达式与错误，保留历史与存储状态；空态时保持引用不变。 */
function clearExpression(state) {
  if (
    state.phase === "empty" &&
    state.tokens.length === 0 &&
    state.error === null &&
    state.notice === null
  ) {
    return state;
  }
  return {
    ...createInitialState(),
    history: state.history,
    storageAvailable: state.storageAvailable,
  };
}

/** @param {CalcState} state @param {string|undefined} value */
function reduceDigit(state, value) {
  if (typeof value !== "string" || !/^[0-9]$/.test(value)) {
    return state;
  }
  if (state.phase === "evaluated" || state.phase === "error") {
    return finalizeEdit(state, [{ type: "num", raw: value }]);
  }

  const tokens = state.tokens;
  const last = tokens[tokens.length - 1];
  if (!last) {
    return finalizeEdit(state, [{ type: "num", raw: value }]);
  }

  if (last.type === "num") {
    if (last.raw.includes("e") || last.raw.includes("E")) {
      return state;
    }
    const nextRaw = last.raw === "0" ? value : `${last.raw}${value}`;
    const notice = numberLimitNotice(nextRaw);
    if (notice) {
      return withNotice(state, notice);
    }
    return finalizeEdit(state, [
      ...tokens.slice(0, -1),
      { type: "num", raw: nextRaw },
    ]);
  }

  if (last.type === "op" || last.type === "lparen") {
    return finalizeEdit(state, [...tokens, { type: "num", raw: value }]);
  }

  // 末尾 `%` / `)` 后接数字会构成隐式乘法，输入层忽略。
  return state;
}

/** @param {CalcState} state */
function reduceDecimal(state) {
  if (state.phase === "evaluated" || state.phase === "error") {
    return finalizeEdit(state, [{ type: "num", raw: "0." }]);
  }

  const tokens = state.tokens;
  const last = tokens[tokens.length - 1];
  if (!last) {
    return finalizeEdit(state, [{ type: "num", raw: "0." }]);
  }

  if (last.type === "num") {
    if (last.raw.includes(".") || last.raw.includes("e") || last.raw.includes("E")) {
      return state;
    }
    const nextRaw = `${last.raw}.`;
    const notice = numberLimitNotice(nextRaw);
    if (notice) {
      return withNotice(state, notice);
    }
    return finalizeEdit(state, [
      ...tokens.slice(0, -1),
      { type: "num", raw: nextRaw },
    ]);
  }

  if (last.type === "op" || last.type === "lparen") {
    return finalizeEdit(state, [...tokens, { type: "num", raw: "0." }]);
  }

  return state;
}

/** @param {CalcState} state @param {string|undefined} value */
function reduceOperator(state, value) {
  if (value !== "+" && value !== "-" && value !== "*" && value !== "/") {
    return state;
  }
  if (state.phase === "error") {
    return state;
  }
  if (state.phase === "empty") {
    return value === "-"
      ? finalizeEdit(state, [{ type: "op", value: "-" }])
      : state;
  }
  if (state.phase === "evaluated") {
    return finalizeEdit(state, [
      { type: "num", raw: state.resultText ?? "0" },
      { type: "op", value },
    ]);
  }

  const tokens = state.tokens;
  const last = tokens[tokens.length - 1];
  if (!last) {
    return state;
  }

  if (last.type === "op") {
    // 一元负号可连续叠加；其他运算符只在二元位置替换上一个运算符。
    if (value === "-") {
      return finalizeEdit(state, [...tokens, { type: "op", value: "-" }]);
    }
    if (!isBinaryOpAt(tokens, tokens.length - 1)) {
      return state;
    }
    return finalizeEdit(state, [...tokens.slice(0, -1), { type: "op", value }]);
  }

  if (last.type === "lparen") {
    return value === "-"
      ? finalizeEdit(state, [...tokens, { type: "op", value: "-" }])
      : state;
  }

  if (isOperandEnd(last)) {
    return finalizeEdit(state, [...tokens, { type: "op", value }]);
  }
  return state;
}

/** @param {CalcState} state */
function reducePercent(state) {
  if (state.phase === "empty" || state.phase === "error") {
    return state;
  }
  if (state.phase === "evaluated") {
    return finalizeEdit(state, [
      { type: "num", raw: state.resultText ?? "0" },
      { type: "percent" },
    ]);
  }
  const tokens = state.tokens;
  if (!isOperandEnd(tokens[tokens.length - 1])) {
    return state;
  }
  return finalizeEdit(state, [...tokens, { type: "percent" }]);
}

/** @param {CalcState} state @param {string|undefined} value */
function reduceParen(state, value) {
  if (value === "(") {
    if (state.phase === "evaluated" || state.phase === "error") {
      return finalizeEdit(state, [{ type: "lparen" }]);
    }
    const tokens = state.tokens;
    const last = tokens[tokens.length - 1];
    if (last && last.type !== "op" && last.type !== "lparen") {
      return state;
    }
    if (openParenDepth(tokens) + 1 > MAX_PAREN_DEPTH) {
      return withNotice(state, ERROR_MESSAGES.E_TOO_DEEP);
    }
    return finalizeEdit(state, [...tokens, { type: "lparen" }]);
  }

  if (value !== ")" || state.phase !== "editing") {
    return state;
  }
  const tokens = state.tokens;
  if (!isOperandEnd(tokens[tokens.length - 1]) || openParenDepth(tokens) <= 0) {
    return state;
  }
  return finalizeEdit(state, [...tokens, { type: "rparen" }]);
}

/** @param {CalcState} state */
function reduceToggleSign(state) {
  if (state.phase === "error") {
    return state;
  }
  if (state.phase === "empty") {
    return finalizeEdit(state, [{ type: "op", value: "-" }]);
  }
  if (state.phase === "evaluated") {
    return finalizeEdit(state, [
      { type: "op", value: "-" },
      { type: "num", raw: state.resultText ?? "0" },
    ]);
  }

  const tokens = state.tokens;
  const last = tokens[tokens.length - 1];
  if (!last) {
    return state;
  }
  if (!isOperandEnd(last)) {
    // 末尾是运算符或 `(`：插入一元负号。
    return finalizeEdit(state, [...tokens, { type: "op", value: "-" }]);
  }

  // 回退到当前操作数起点：跳过尾部 `%`，再匹配括号组。
  let start = tokens.length - 1;
  while (start >= 0 && tokens[start].type === "percent") {
    start -= 1;
  }
  if (start < 0) {
    return state;
  }
  if (tokens[start].type === "rparen") {
    let depth = 0;
    for (; start >= 0; start -= 1) {
      if (tokens[start].type === "rparen") {
        depth += 1;
      } else if (tokens[start].type === "lparen") {
        depth -= 1;
        if (depth === 0) {
          break;
        }
      }
    }
  }
  if (start < 0) {
    return state;
  }

  const previous = tokens[start - 1];
  const hasUnaryMinus =
    previous !== undefined &&
    previous.type === "op" &&
    previous.value === "-" &&
    !isBinaryOpAt(tokens, start - 1);

  if (hasUnaryMinus) {
    return finalizeEdit(state, [
      ...tokens.slice(0, start - 1),
      ...tokens.slice(start),
    ]);
  }
  return finalizeEdit(state, [
    ...tokens.slice(0, start),
    { type: "op", value: "-" },
    ...tokens.slice(start),
  ]);
}

/** @param {CalcState} state @param {{id?: string, createdAt?: string}} action */
function reduceEvaluate(state, action) {
  if (state.phase !== "editing") {
    return state;
  }

  const parsed = parse(state.tokens);
  if (!parsed.ok) {
    return withEvaluationError(state, parsed.error);
  }
  const evaluated = evaluate(parsed.ast);
  if (!evaluated.ok) {
    return withEvaluationError(state, evaluated.error);
  }

  const resultText = formatNumber(evaluated.value);
  const entry = {
    id: typeof action.id === "string" && action.id.length > 0 ? action.id : generateId(),
    expression: serialize(state.tokens),
    result: resultText,
    createdAt:
      typeof action.createdAt === "string"
        ? action.createdAt
        : new Date().toISOString(),
  };

  return {
    ...state,
    phase: "evaluated",
    result: evaluated.value,
    resultText,
    previewText: null,
    error: null,
    notice: null,
    history: appendHistory(state.history, entry),
  };
}

/** @param {CalcState} state @param {import("../core/errors.js").CalcError} error */
function withEvaluationError(state, error) {
  return {
    ...state,
    phase: "error",
    result: null,
    resultText: null,
    previewText: null,
    error,
    notice: null,
  };
}

/** @param {CalcState} state */
function reduceDeleteBack(state) {
  if (state.phase === "empty") {
    return state;
  }

  const tokens = state.tokens.slice();
  const last = tokens[tokens.length - 1];
  if (!last) {
    return clearExpression(state);
  }

  // 普通数字按字符退格；运算符/括号/百分号/科学计数数字按 token 删除。
  if (
    last.type === "num" &&
    last.raw.length > 1 &&
    !last.raw.includes("e") &&
    !last.raw.includes("E")
  ) {
    const raw = last.raw.slice(0, -1);
    if (raw === "" || raw === ".") {
      tokens.pop();
    } else {
      tokens[tokens.length - 1] = { type: "num", raw };
    }
  } else {
    tokens.pop();
  }

  return finalizeEdit(state, tokens);
}

/** @param {CalcState} state @param {string|undefined} id */
function reduceLoadHistory(state, id) {
  if (typeof id !== "string") {
    return state;
  }
  const entry = state.history.find((item) => item.id === id);
  if (!entry) {
    return state;
  }
  const tokenized = tokenize(entry.expression);
  return tokenized.ok ? finalizeEdit(state, tokenized.tokens) : state;
}
