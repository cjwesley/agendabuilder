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

async function exportPng(btn) {
  const url = btn.dataset.renderUrl;
  const originalLabel = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Rendering…";
  try {
    const resp = await fetch(url, { method: "POST" });
    const body = await resp.json();
    if (resp.ok) {
      btn.textContent = "Export PNG";
      const links = [];
      if (body.html) links.push(`<a href="${body.html}" target="_blank">HTML</a>`);
      if (body.png) links.push(`<a href="${body.png}" target="_blank">PNG</a>`);
      showFlash(`Exported: ${links.join(" · ")}`, "ok");
    } else if (resp.status === 207) {
      btn.textContent = "Export PNG";
      const htmlLink = body.html
        ? `<a href="${body.html}" target="_blank">HTML</a>`
        : "(no html)";
      showFlash(
        `HTML exported (${htmlLink}); PNG failed: ${body.error || "(no detail)"}`,
        "err"
      );
    } else {
      btn.textContent = "Export PNG";
      showFlash(`Export failed: ${body.error || resp.statusText}`, "err");
    }
  } catch (e) {
    btn.textContent = "Export PNG";
    showFlash(`Export failed: ${e.message}`, "err");
  } finally {
    btn.disabled = false;
  }
}

function showFlash(html, kind) {
  let host = document.querySelector(".form-pane-inner");
  if (!host) return;
  let flash = host.querySelector(".flash.transient");
  if (!flash) {
    flash = document.createElement("div");
    flash.className = "flash transient";
    host.insertBefore(flash, host.firstChild);
  }
  flash.classList.remove("ok", "err");
  if (kind) flash.classList.add(kind);
  flash.innerHTML = html;
  setTimeout(() => {
    if (flash.parentElement) flash.parentElement.removeChild(flash);
  }, 8000);
}

document.addEventListener("DOMContentLoaded", () => {
  setMode(currentMode());
  attachCharCounters();

  document.querySelectorAll(".mode-radio").forEach(r => {
    r.addEventListener("change", e => setMode(e.target.value));
  });

  const exportBtn = document.getElementById("export-png");
  if (exportBtn) exportBtn.addEventListener("click", () => exportPng(exportBtn));

  const pullBtn = document.getElementById("legistar-pull");
  if (pullBtn) pullBtn.addEventListener("click", () => legistarPullFlow(pullBtn));
});

async function legistarPullFlow(btn) {
  btn.disabled = true;
  btn.textContent = "Loading events…";
  try {
    const r = await fetch("/legistar/events");
    const body = await r.json();
    if (!r.ok) {
      showFlash(`Legistar lookup failed: ${body.error || r.statusText}`, "err");
      return;
    }
    const events = body.events || [];
    if (events.length === 0) {
      showFlash("No upcoming Board events found.", "err");
      return;
    }
    const labels = events.map((e, i) => `${i + 1}. ${e.date || "?"} — event ${e.event_id} (${e.agenda_status || "no status"})`);
    const choice = prompt(
      "Pick an event by number:\n" + labels.join("\n"),
      "1"
    );
    if (!choice) return;
    const idx = parseInt(choice, 10) - 1;
    if (Number.isNaN(idx) || idx < 0 || idx >= events.length) {
      showFlash("Invalid selection.", "err");
      return;
    }
    btn.textContent = "Importing…";
    const importResp = await fetch("/legistar/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_id: events[idx].event_id }),
    });
    const importBody = await importResp.json();
    if (!importResp.ok) {
      showFlash(`Import failed: ${importBody.error || importResp.statusText}`, "err");
      return;
    }
    showFlash(
      `Imported issue ${importBody.issue_number} for ${importBody.date} (${importBody.triage_count} triage). Redirecting…`,
      "ok"
    );
    setTimeout(() => { window.location.href = importBody.edit_url; }, 1200);
  } finally {
    btn.disabled = false;
    btn.textContent = "Pull from Legistar";
  }
}
