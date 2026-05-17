# Pinned Playwright image — Chromium + system deps preinstalled.
FROM mcr.microsoft.com/playwright/python:v1.59.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

# uv is the project's package manager; install via the standalone binary.
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /usr/local/bin/uv

# Install deps first (cached layer) — copy lockfile + pyproject only.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Now the app code.
COPY . .

# Install the project itself into the locked env.
RUN uv sync --frozen

EXPOSE 8080

# Use gunicorn for production — 2 sync workers fit the 1024MB shared-CPU machine.
# A single-worker fly setup would also work for solo use, but 2 lets a slow
# Playwright render not block a preview request.
CMD ["gunicorn", "-w", "2", "--timeout", "120", "-b", "0.0.0.0:8080", "app:app"]
