/**
 * 递归下降语法分析：Token[] → AST（architecture.md §5.2）。
 * 文法：additive → multiplicative (("+"|"-") multiplicative)*；
 * multiplicative → unary (("*"|"/") unary)*；unary → 符号 unary | postfix；
 * postfix → primary "%"*；primary → NUMBER | "(" expression ")"。
 * 公开接口不抛异常。
 */

import { createError } from "./errors.js";
import { MAX_PAREN_DEPTH } from "./limits.js";

/** @typedef {import("./tokenizer.js").Token} Token */
/** @typedef {{type:"num", value:number, raw:string} | {type:"unary", op:"+"|"-", operand:Node} | {type:"percent", operand:Node} | {type:"binary", op:"+"|"-"|"*"|"/", left:Node, right:Node}} Node */

class ParseFailure extends Error {
  /** @param {import("./errors.js").CalcError} error */
  constructor(error) {
    super(error.message);
    this.name = "ParseFailure";
    this.error = error;
  }
}

/** @param {string} code @param {number} position */
function failAt(code, position) {
  throw new ParseFailure(createError(code, { position }));
}

/**
 * @param {Token[]} tokens
 * @returns {{ok: true, ast: Node} | {ok: false, error: import("./errors.js").CalcError}}
 */
export function parse(tokens) {
  if (!Array.isArray(tokens)) {
    return {
      ok: false,
      error: createError("E_SYNTAX", { detail: "tokens must be an array" }),
    };
  }
  if (tokens.length === 0) {
    return { ok: false, error: createError("E_SYNTAX", { position: 0 }) };
  }

  const state = { tokens, index: 0, depth: 0 };
  try {
    const ast = parseAdditive(state);
    if (state.index < tokens.length) {
      const token = tokens[state.index];
      if (token.type === "rparen") {
        failAt("E_UNBALANCED_PAREN", token.start);
      }
      if (token.type === "num" || token.type === "lparen") {
        failAt("E_IMPLICIT_MUL", token.start);
      }
      failAt("E_SYNTAX", token.start);
    }
    return { ok: true, ast };
  } catch (error) {
    if (error instanceof ParseFailure) {
      return { ok: false, error: error.error };
    }
    return {
      ok: false,
      error: createError("E_UNKNOWN", {
        detail: error instanceof Error ? error.message : String(error),
      }),
    };
  }
}

/** @param {{tokens: Token[], index: number, depth: number}} state @returns {Node} */
function parseAdditive(state) {
  let left = parseMultiplicative(state);
  while (state.index < state.tokens.length) {
    const token = state.tokens[state.index];
    if (token.type !== "op" || (token.value !== "+" && token.value !== "-")) {
      break;
    }
    state.index += 1;
    const right = parseMultiplicative(state);
    left = { type: "binary", op: token.value, left, right };
  }
  return left;
}

/** @param {{tokens: Token[], index: number, depth: number}} state @returns {Node} */
function parseMultiplicative(state) {
  let left = parseUnary(state);
  while (state.index < state.tokens.length) {
    const token = state.tokens[state.index];
    if (token.type !== "op" || (token.value !== "*" && token.value !== "/")) {
      break;
    }
    state.index += 1;
    const right = parseUnary(state);
    left = { type: "binary", op: token.value, left, right };
  }
  return left;
}

/** @param {{tokens: Token[], index: number, depth: number}} state @returns {Node} */
function parseUnary(state) {
  const token = state.tokens[state.index];
  if (token && token.type === "op" && (token.value === "+" || token.value === "-")) {
    state.index += 1;
    return { type: "unary", op: token.value, operand: parseUnary(state) };
  }
  return parsePostfix(state);
}

/** @param {{tokens: Token[], index: number, depth: number}} state @returns {Node} */
function parsePostfix(state) {
  let node = parsePrimary(state);
  while (state.index < state.tokens.length) {
    const token = state.tokens[state.index];
    if (token.type !== "percent") {
      break;
    }
    state.index += 1;
    node = { type: "percent", operand: node };
  }
  return node;
}

/** @param {{tokens: Token[], index: number, depth: number}} state @returns {Node} */
function parsePrimary(state) {
  const token = state.tokens[state.index];
  if (!token) {
    const end =
      state.tokens.length > 0 ? (state.tokens[state.tokens.length - 1].end ?? 0) : 0;
    failAt("E_SYNTAX", end);
  }

  if (token.type === "num") {
    state.index += 1;
    const value = Number(token.raw);
    if (!Number.isFinite(value)) {
      failAt("E_OVERFLOW", token.start);
    }
    return { type: "num", value, raw: token.raw };
  }

  if (token.type === "lparen") {
    state.index += 1;
    state.depth += 1;
    if (state.depth > MAX_PAREN_DEPTH) {
      failAt("E_TOO_DEEP", token.start);
    }
    const next = state.tokens[state.index];
    if (!next || next.type === "rparen") {
      failAt("E_UNBALANCED_PAREN", next ? next.start : token.start);
    }
    const inner = parseAdditive(state);
    const closing = state.tokens[state.index];
    if (!closing || closing.type !== "rparen") {
      if (closing && (closing.type === "num" || closing.type === "lparen")) {
        failAt("E_IMPLICIT_MUL", closing.start);
      }
      failAt("E_UNBALANCED_PAREN", token.start);
    }
    state.index += 1;
    state.depth -= 1;
    return inner;
  }

  if (token.type === "rparen") {
    failAt("E_UNBALANCED_PAREN", token.start);
  }
  failAt("E_SYNTAX", token.start);
}
