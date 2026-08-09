import { copyText } from "./clipboard.js";

const COPY_FEEDBACK_MS = 2000;
const copyTimers = new WeakMap();

function setCopyFeedback(button, copied) {
  const text = button.querySelector(".copy-text");
  const label = copied ? button.dataset.labelCopied : button.dataset.labelCopy;

  if (text) text.textContent = label || "";

  button.classList.toggle("text-copied", copied);
  button.title = label || "";
  button.setAttribute("aria-label", label || "");
}

async function handleCopy(button) {
  const group = button.closest("[data-term-group]");
  if (!group) return;

  const copied = await copyText(group.dataset.copy ?? "");
  if (!copied) return;

  setCopyFeedback(button, true);

  const previousTimer = copyTimers.get(button);
  if (previousTimer) {
    window.clearTimeout(previousTimer);
  }

  const timer = window.setTimeout(() => {
    setCopyFeedback(button, false);
    copyTimers.delete(button);
  }, COPY_FEEDBACK_MS);

  copyTimers.set(button, timer);
}

function handleClick(event) {
  const button = event.target.closest("[data-term-copy]");
  if (!button) return;
  event.preventDefault();
  handleCopy(button);
}

let initialized = false;

export function initTermBlocks(root = document) {
  if (initialized) return;
  initialized = true;

  document.addEventListener("click", handleClick);
}

// 自引导：term.js 仅在页面包含 term 代码块时被条件加载（见 head/js.html），
// 因此模块加载即注册事件，无需从 main.js 调用。
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initTermBlocks, { once: true });
} else {
  initTermBlocks();
}
