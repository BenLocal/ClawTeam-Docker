/**
 * 数值 → 展示字符串（见 docs/architecture.md §5.4）。
 * 规则：15 位有效数字稳定化；|x| >= 1e16 或 0 < |x| < 1e-6 用科学计数法；
 * 负零显示 0；不使用千分位与本地化分隔符。
 */

/**
 * 去掉科学计数法尾数多余的 0，并保留指数原样（如 `e+16`、`e-7`）。
 *
 * @param {string} exponential `Number.prototype.toExponential` 的输出
 * @returns {string}
 */
function trimExponential(exponential) {
  const [mantissa, exponent] = exponential.split("e");
  const trimmed = mantissa.replace(/\.?0+$/, "");
  return `${trimmed}e${exponent}`;
}

/**
 * @param {number} value 调用方应保证为有限数；非有限值按 0 处理（防御性）
 * @returns {string}
 */
export function formatNumber(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "0";
  }
  if (Object.is(value, -0)) {
    return "0";
  }

  const normalized = Number(value.toPrecision(15));
  if (Object.is(normalized, -0) || normalized === 0) {
    return "0";
  }

  const abs = Math.abs(normalized);
  if (abs >= 1e16 || abs < 1e-6) {
    return trimExponential(normalized.toExponential(14));
  }

  return String(normalized);
}
