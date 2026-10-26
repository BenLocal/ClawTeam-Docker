/** 物理键盘映射（architecture.md §9）；只派发与按钮相同的动作。 */

import {
  clearAll,
  decimal,
  deleteBack,
  digit,
  evaluate,
  operator,
  paren,
  percent,
  toggleSign,
} from "../app/actions.js";

/** @param {Element | null} target @returns {boolean} */
function isEditable(target) {
  if (!target) {
    return false;
  }
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
    return true;
  }
  return target instanceof HTMLElement && target.isContentEditable;
}

/** @param {{store: object, historyView?: object|null, target?: Document|HTMLElement}} options */
export function createKeyboard({ store, historyView = null, target = document }) {
  /** @param {KeyboardEvent} event */
  function handleKeydown(event) {
    if (event.defaultPrevented || event.isComposing) {
      return;
    }
    if (event.ctrlKey || event.altKey || event.metaKey) {
      return;
    }
    if (isEditable(event.target instanceof Element ? event.target : null)) {
      return;
    }

    const key = event.key;

    // 聚焦在按钮上时把 Enter / 空格留给原生按钮激活。
    if (
      event.target instanceof HTMLElement &&
      event.target.tagName === "BUTTON" &&
      (key === "Enter" || key === " ")
    ) {
      return;
    }

    /** @type {object | null} */
    let action = null;

    if (/^[0-9]$/.test(key)) {
      action = digit(key);
    } else if (key === ".") {
      action = decimal();
    } else if (key === "+") {
      action = operator("+");
    } else if (key === "-") {
      action = operator("-");
    } else if (key === "*" || key === "x" || key === "X") {
      action = operator("*");
    } else if (key === "/") {
      action = operator("/");
    } else if (key === "%") {
      action = percent();
    } else if (key === "(") {
      action = paren("(");
    } else if (key === ")") {
      action = paren(")");
    } else if (key === "Enter" || key === "=") {
      action = evaluate();
    } else if (key === "Backspace") {
      action = deleteBack();
    } else if (key === "Delete") {
      action = clearAll();
    } else if (key === "Escape") {
      if (historyView && historyView.isOpen()) {
        event.preventDefault();
        historyView.close();
        return;
      }
      action = clearAll();
    } else if (key === "F9") {
      action = toggleSign();
    } else if (key === "h" || key === "H") {
      if (historyView) {
        event.preventDefault();
        historyView.toggle();
      }
      return;
    }

    if (action) {
      event.preventDefault();
      store.dispatch(action);
    }
  }

  target.addEventListener("keydown", /** @type {EventListener} */ (handleKeydown));

  return () => {
    target.removeEventListener(
      "keydown",
      /** @type {EventListener} */ (handleKeydown),
    );
  };
}
