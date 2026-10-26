/**
 * AST 求值（见 docs/architecture.md §5.3）。
 * 纯函数，无 DOM、无格式化输出。
 */

import { createError } from "./errors.js";

/** @typedef {import("./parser.js").Node} Node */

class EvalFailure extends Error {
  /** @param {import("./errors.js").CalcError} error */
  constructor(error) {
    super(error.message);
    this.name = "EvalFailure";
    this.error = error;
  }
}

/** @param {string} code */
function fail(code) {
  throw new EvalFailure(createError(code));
}

/**
 * @param {Node} node
 * @returns {number}
 */
function evaluateNode(node) {
  if (!node || typeof node !== "object") {
    fail("E_UNKNOWN");
  }

  switch (node.type) {
    case "num": {
      const value = Number(node.raw);
      if (!Number.isFinite(value)) {
        fail("E_OVERFLOW");
      }
      return value;
    }
    case "unary": {
      const operand = evaluateNode(node.operand);
      return node.op === "-" ? -operand : operand;
    }
    case "percent": {
      const value = evaluateNode(node.operand) / 100;
      if (Number.isNaN(value)) {
        fail("E_UNKNOWN");
      }
      if (!Number.isFinite(value)) {
        fail("E_OVERFLOW");
      }
      return value;
    }
    case "binary": {
      const left = evaluateNode(node.left);
      const right = evaluateNode(node.right);
      if (node.op === "/") {
        if (right === 0) {
          fail("E_DIV_ZERO");
        }
        const quotient = left / right;
        if (Number.isNaN(quotient)) {
          fail("E_UNKNOWN");
        }
        if (!Number.isFinite(quotient)) {
          fail("E_OVERFLOW");
        }
        return quotient;
      }
      let result;
      if (node.op === "+") {
        result = left + right;
      } else if (node.op === "-") {
        result = left - right;
      } else if (node.op === "*") {
        result = left * right;
      } else {
        fail("E_UNKNOWN");
      }
      if (Number.isNaN(result)) {
        fail("E_UNKNOWN");
      }
      if (!Number.isFinite(result)) {
        fail("E_OVERFLOW");
      }
      return result;
    }
    default:
      fail("E_UNKNOWN");
  }
}

/**
 * @param {Node} ast
 * @returns {{ok: true, value: number} | {ok: false, error: import("./errors.js").CalcError}}
 */
export function evaluate(ast) {
  try {
    const value = evaluateNode(ast);
    if (Number.isNaN(value)) {
      return { ok: false, error: createError("E_UNKNOWN") };
    }
    if (!Number.isFinite(value)) {
      return { ok: false, error: createError("E_OVERFLOW") };
    }
    return { ok: true, value };
  } catch (error) {
    if (error instanceof EvalFailure) {
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
