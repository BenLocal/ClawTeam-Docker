/**
 * Token[] → 表达式显示字符串（见 docs/architecture.md §5.5）。
 * 输出必须能被 tokenize 重新解析（历史重放）。
 */

/** @typedef {import("./tokenizer.js").Token} Token */

const OP_DISPLAY = Object.freeze({
  "+": "+",
  "-": "−",
  "*": "×",
  "/": "÷",
});

/** 前一个 token 是操作数结束（数字/`%`/`)`）时，该位置运算符为二元。 */
export function isBinaryOpAt(tokens, index) {
  const token = tokens[index];
  if (!token || token.type !== "op") {
    return false;
  }
  const previous = tokens[index - 1];
  if (!previous) {
    return false;
  }
  return isOperandEnd(previous);
}

/** @param {Token | undefined} token @returns {boolean} */
export function isOperandEnd(token) {
  return (
    token !== undefined &&
    (token.type === "num" || token.type === "percent" || token.type === "rparen")
  );
}

/**
 * @param {Token} token
 * @returns {string}
 */
function tokenDisplay(token) {
  switch (token.type) {
    case "num":
      return token.raw;
    case "op":
      return OP_DISPLAY[token.value];
    case "lparen":
      return "(";
    case "rparen":
      return ")";
    case "percent":
      return "%";
    default:
      return "";
  }
}

/**
 * @param {Token[]} tokens
 * @returns {string}
 */
export function serialize(tokens) {
  let output = "";
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    const previous = tokens[index - 1];

    if (previous) {
      const previousIsBinaryOp = isBinaryOpAt(tokens, index - 1);
      const tokenIsBinaryOp = isBinaryOpAt(tokens, index);
      if (previousIsBinaryOp) {
        output += " ";
      } else if (tokenIsBinaryOp && isOperandEnd(previous)) {
        output += " ";
      }
    }

    output += tokenDisplay(token);
  }
  return output;
}
