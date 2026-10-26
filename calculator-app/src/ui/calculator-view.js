/** 计算器视图：渲染显示区、事件委托、运算符激活态（architecture.md §5.6）。 */

import { serialize } from "../core/serializer.js";
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
import { setHidden, setText } from "./dom.js";

/** @param {HTMLElement} button @returns {object | null} */
function actionForButton(button) {
  const { action, value } = button.dataset;
  switch (action) {
    case "digit":
      return digit(value ?? "");
    case "decimal":
      return decimal();
    case "operator":
      return operator(/** @type {"+"|"-"|"*"|"/"} */ (value));
    case "percent":
      return percent();
    case "paren":
      return paren(/** @type {"("|")"} */ (value));
    case "toggleSign":
      return toggleSign();
    case "evaluate":
      return evaluate();
    case "clearAll":
      return clearAll();
    case "deleteBack":
      return deleteBack();
    default:
      return null;
  }
}

/** @param {{store: object, root?: Document|HTMLElement}} options */
export function createCalculatorView({ store, root = document }) {
  const expressionEl = root.querySelector('[data-role="expression"]');
  const resultEl = root.querySelector('[data-role="result"]');
  const errorEl = root.querySelector('[data-role="error"]');
  const noticeEl = root.querySelector('[data-role="notice"]');
  const storageNoteEl = root.querySelector('[data-role="storage-note"]');
  const keypad = root.querySelector('[data-role="keypad"]');
  const operatorButtons = [...root.querySelectorAll('[data-action="operator"]')];

  if (keypad) {
    keypad.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof Element)) {
        return;
      }
      const button = target.closest("button[data-action]");
      if (!(button instanceof HTMLButtonElement) || !keypad.contains(button)) {
        return;
      }
      const action = actionForButton(button);
      if (action) {
        store.dispatch(action);
      }
    });
  }

  /** @param {import("../app/state.js").CalcState} state */
  function render(state) {
    const expression = serialize(state.tokens);
    setText(expressionEl, expression);
    if (expressionEl) {
      expressionEl.scrollLeft = expressionEl.scrollWidth;
    }

    let resultText = "";
    let isPreview = false;
    if (state.phase === "evaluated") {
      resultText = state.resultText ?? "";
    } else if (state.phase === "editing") {
      if (state.previewText !== null) {
        resultText = state.previewText;
        isPreview = true;
      }
    } else if (state.phase === "empty") {
      resultText = "0";
    }

    setText(resultEl, resultText);
    if (resultEl) {
      resultEl.classList.toggle("is-preview", isPreview && state.error === null);
    }

    setText(errorEl, state.error ? state.error.message : "");
    setText(noticeEl, state.notice ?? "");
    setHidden(storageNoteEl, state.storageAvailable);

    const lastToken = state.tokens[state.tokens.length - 1];
    for (const button of operatorButtons) {
      const active =
        lastToken !== undefined &&
        lastToken.type === "op" &&
        button.dataset.value === lastToken.value;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    }
  }

  const unsubscribe = store.subscribe(render);
  render(store.getState());

  return { unsubscribe };
}
