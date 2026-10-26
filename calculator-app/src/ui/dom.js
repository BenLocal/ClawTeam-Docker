/** DOM 辅助：只用 textContent 写入文本，避免 HTML 注入。 */

/** @param {Element|null|undefined} element @param {string|null|undefined} value */
export function setText(element, value) {
  if (!element) {
    return;
  }
  const next = value ?? "";
  if (element.textContent !== next) {
    element.textContent = next;
  }
}

/** @param {Element|null|undefined} element @param {boolean} hidden */
export function setHidden(element, hidden) {
  if (!element) {
    return;
  }
  element.hidden = Boolean(hidden);
}

/** @param {Element} element */
export function clearChildren(element) {
  while (element.firstChild) {
    element.removeChild(element.firstChild);
  }
}

/** @template {keyof HTMLElementTagNameMap} K @param {K} tag @param {string} [className] @param {string} [text] @returns {HTMLElementTagNameMap[K]} */
export function createElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) {
    element.className = className;
  }
  if (text !== undefined) {
    element.textContent = text;
  }
  return element;
}
