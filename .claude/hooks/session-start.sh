#!/bin/bash
# SessionStart hook for The Agenda Engine.
#
# Runs only in Claude Code on the web (`$CLAUDE_CODE_REMOTE == "true"`).
# Idempotent — safe to re-run on resume/clear/compact.
#
# Installs:
#   - Python deps via `uv sync` (uses uv.lock; cached after first run)
#   - flyctl (only if missing)
#
# Exports for the session (via $CLAUDE_ENV_FILE):
#   - PLAYWRIGHT_BROWSERS_PATH — so render-pipeline tests find the bundled Chromium
#   - PATH addition for flyctl

set -euo pipefail

# Local-machine sessions: do nothing.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

# ---------- 1. Python deps ----------
if command -v uv >/dev/null 2>&1; then
  echo "[hook] uv sync"
  uv sync --frozen
else
  echo "[hook] WARNING: uv not on PATH; skipping uv sync"
fi

# ---------- 2. Playwright Chromium path ----------
# The container preinstalls Chromium at /opt/pw-browsers; expose it so PNG
# render tests don't skip and so the editor's Export-PNG button works in dev.
if [ -d /opt/pw-browsers ]; then
  echo 'export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers' >> "$CLAUDE_ENV_FILE"
fi

# ---------- 3. flyctl (best-effort — network policy may block fly.io) ----------
if ! command -v flyctl >/dev/null 2>&1; then
  echo "[hook] installing flyctl"
  if ! curl -fsSL https://fly.io/install.sh 2>/dev/null | sh >/dev/null 2>&1; then
    echo "[hook] flyctl install failed (fly.io likely blocked by network policy);" \
         "skipping. Set the environment to allow fly.io egress to enable deploys."
  fi
fi

# Make flyctl visible to the session regardless of where it landed.
if [ -d "$HOME/.fly/bin" ]; then
  echo "export PATH=\"$HOME/.fly/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi

echo "[hook] done"
