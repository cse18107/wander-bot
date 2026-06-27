# syntax=docker/dockerfile:1
# Multi-stage build. Slim, non-root, deterministic installs via uv.

FROM python:3.12-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY mcp_server ./mcp_server
COPY README.md ./
RUN uv pip install --system --no-cache .

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# non-root user
RUN useradd --create-home --uid 10001 wander
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY src ./src
COPY mcp_server ./mcp_server
ENV PYTHONPATH=/app/src
USER wander
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz').status==200 else 1)"
CMD ["uvicorn", "wanderbot.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
