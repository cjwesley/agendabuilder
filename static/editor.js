/* ============================================================
   Editor behaviour:
   - Live / Manual render mode toggle (persists in localStorage)
   - Debounced HTMX preview refresh on input
   - Character counters on guardrail fields
   ============================================================ */

const LS_MODE_KEY = "agenda.renderMode";  // "live" | "manual"
const LIVE_TRIGGER = "input changed delay:300ms, change";
const MANUAL_TRIGGER = "click from:#render-now";

function currentMode() {
  return localStorage.getItem(LS_MODE_KEY) || "live";
}

function setMode(mode) {
  localStorage.setItem(LS_MODE_KEY, mode);
  const form = document.getElementById("issue-form");
  if (!form) return;
  form.setAttribute("hx-trigger", mode === "live" ? LIVE_TRIGGER : MANUAL_TRIGGER);
  // HTMX caches the trigger attribute; tell it to re-process.
  if (window.htmx) window.htmx.process(form);

  // Update UI
  document.querySelectorAll(".mode-radio").forEach(r => {
    r.checked = r.value === mode;
  });
  const renderBtn = document.getElementById("render-now");
  if (renderBtn) renderBtn.style.display = mode === "manual" ? "" : "none";
}

function attachCharCounters() {
  // Any [data-maxlen] field gets a counter; threshold colors at 90% / 100%.
  document.querySelectorAll("[data-maxlen]").forEach(input => {
    const max = parseInt(input.dataset.maxlen, 10);
    const counter = input.parentElement.querySelector(".charcount");
    if (!counter) return;
    const update = () => {
      const n = input.value.length;
      counter.textContent = `${n}/${max}`;
      counter.classList.toggle("warn", n > Math.floor(max * 0.9) && n <= max);
      counter.classList.toggle("err", n > max);
    };
    input.addEventListener("input", update);
    update();
  });
}

// Re-attach handlers when HTMX swaps in new form content (rare in this app —
// preview swaps target the preview pane, not the form).
document.body.addEventListener("htmx:afterSwap", attachCharCounters);

document.addEventListener("DOMContentLoaded", () => {
  setMode(currentMode());
  attachCharCounters();

  document.querySelectorAll(".mode-radio").forEach(r => {
    r.addEventListener("change", e => setMode(e.target.value));
  });
});
