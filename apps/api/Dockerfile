FROM ghcr.io/astral-sh/uv:0.13.1 AS uv
FROM python:3.14-slim AS base
COPY --from=uv /uv /uvx /bin/
WORKDIR /workspace
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PYTHONPATH=/workspace/apps/api
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY apps/api ./apps/api
COPY scripts ./scripts
ENV PATH="/workspace/.venv/bin:$PATH"
RUN useradd --create-home app
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS test
USER root
RUN uv sync --frozen
USER app
CMD ["pytest"]
