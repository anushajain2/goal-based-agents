# Autopilot backend: one image for the API (default command) and the worker
# (command: python -m app.worker). Built by Render from render.yaml; also runs locally:
#   docker build -t autopilot-backend backend
#   docker run -p 8000:8000 -e ENVIRONMENT=development autopilot-backend
FROM python:3.12-slim AS build
RUN pip install --no-cache-dir "uv==0.11.*"
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 autopilot
WORKDIR /app
COPY --from=build --chown=autopilot:autopilot /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PORT=8000 \
    DATA_DIR=/tmp/autopilot ENVIRONMENT=production \
    DATABASE_URL=sqlite+aiosqlite:////tmp/autopilot/autopilot.db
USER autopilot
EXPOSE 8000
# DATABASE_URL above is only a fallback for trying the image; Render sets the real one.
# Render terminates TLS and forwards the client's scheme/IP; trust those headers.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --timeout-graceful-shutdown 20"]
