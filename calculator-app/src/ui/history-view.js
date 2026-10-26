/** 历史面板：列表、载入、清空、移动端开合（architecture.md §5.6、§10.3）。 */

import { clearHistory, loadHistory } from "../app/actions.js";
import { clearChildren, createElement, setHidden } from "./dom.js";

/** @param {{store: object, root?: Document|HTMLElement}} options */
export function createHistoryView({ store, root = document }) {
  const panel = root.querySelector('[data-role="history-panel"]');
  const list = root.querySelector('[data-role="history-list"]');
  const emptyEl = root.querySelector('[data-role="history-empty"]');
  const clearBtn = root.querySelector('[data-role="history-clear"]');
  const toggleBtn = root.querySelector('[data-role="history-toggle"]');

  let open = false;
  /** @type {unknown} */
  let renderedHistory = null;

  function setOpen(next) {
    const wasOpen = open;
    open = Boolean(next);
    if (panel) {
      panel.classList.toggle("is-open", open);
    }
    if (toggleBtn) {
      toggleBtn.setAttribute("aria-expanded", open ? "true" : "false");
    }
    if (open) {
      const firstItem = list?.querySelector("button");
      if (firstItem instanceof HTMLElement) {
        firstItem.focus();
      } else if (toggleBtn instanceof HTMLElement) {
        toggleBtn.focus();
      }
    } else if (wasOpen && toggleBtn instanceof HTMLElement) {
      toggleBtn.focus();
    }
  }

  function isOpen() {
    return open;
  }

  function close() {
    if (open) {
      setOpen(false);
    }
  }

  function toggle() {
    setOpen(!open);
  }

  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => setOpen(!open));
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      if (store.getState().history.length === 0) {
        return;
      }
      const confirmed =
        typeof globalThis.confirm !== "function" ||
        globalThis.confirm("确定清空全部历史记录？");
      if (confirmed) {
        store.dispatch(clearHistory());
      }
    });
  }

  if (list) {
    list.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof Element)) {
        return;
      }
      const button = target.closest("button[data-history-id]");
      if (!(button instanceof HTMLButtonElement)) {
        return;
      }
      const id = button.dataset.historyId;
      if (id) {
        store.dispatch(loadHistory(id));
      }
    });
  }

  /** @param {import("../app/state.js").CalcState} state */
  function render(state) {
    if (state.history === renderedHistory) {
      return;
    }
    renderedHistory = state.history;

    if (list) {
      clearChildren(list);
      for (const entry of state.history) {
        const item = createElement("li", "history-item-wrap");
        const button = createElement("button", "history-item");
        button.type = "button";
        button.dataset.historyId = entry.id;
        button.setAttribute("aria-label", `${entry.expression} = ${entry.result}`);
        button.append(
          createElement("span", "history-item-expression", entry.expression),
          createElement("span", "history-item-result", entry.result),
        );
        item.append(button);
        list.append(item);
      }
    }

    setHidden(emptyEl, state.history.length > 0);
    setHidden(list, state.history.length === 0);

    if (clearBtn instanceof HTMLButtonElement) {
      clearBtn.disabled = state.history.length === 0;
    }
  }

  const unsubscribe = store.subscribe(render);
  render(store.getState());
  setOpen(false);

  return { unsubscribe, isOpen, close, toggle };
}
