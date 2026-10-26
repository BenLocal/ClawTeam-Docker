/**
 * 测试辅助：把「分词 → 解析 → 求值 → 格式化」串起来。
 * 仅测试使用，不进入运行时。
 */

import { tokenize } from "../src/core/tokenizer.js";
import { parse } from "../src/core/parser.js";
import { evaluate } from "../src/core/evaluator.js";
import { formatNumber } from "../src/core/formatter.js";

/**
 * @param {string} expression
 * @returns {{
 *   ok: true,
 *   value: number,
 *   text: string,
 *   tokens: import("../src/core/tokenizer.js").Token[],
 *   ast: import("../src/core/parser.js").Node
 * } | {ok: false, error: import("../src/core/errors.js").CalcError}}
 */
export function calc(expression) {
  const tokenized = tokenize(expression);
  if (!tokenized.ok) {
    return tokenized;
  }
  const parsed = parse(tokenized.tokens);
  if (!parsed.ok) {
    return parsed;
  }
  const evaluated = evaluate(parsed.ast);
  if (!evaluated.ok) {
    return evaluated;
  }
  return {
    ok: true,
    value: evaluated.value,
    text: formatNumber(evaluated.value),
    tokens: tokenized.tokens,
    ast: parsed.ast,
  };
}

/**
 * 去掉位置信息，便于比较两次 tokenize 的结果是否等价。
 *
 * @param {import("../src/core/tokenizer.js").Token[]} tokens
 */
export function tokenShape(tokens) {
  return tokens.map((token) => {
    if (token.type === "num") {
      return { type: "num", raw: token.raw };
    }
    if (token.type === "op") {
      return { type: "op", value: token.value };
    }
    return { type: token.type };
  });
}

/**
 * @param {string} id
 * @param {string} expression
 * @param {string} result
 * @param {string} [createdAt]
 */
export function historyEntry(
  id,
  expression,
  result,
  createdAt = "2026-10-26T00:00:00.000Z",
) {
  return { id, expression, result, createdAt };
}
