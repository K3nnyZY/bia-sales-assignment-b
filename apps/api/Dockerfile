FROM ghcr.io/astral-sh/uv:0.13.1 AS uv
FROM python:3.14-slim AS base
COPY --from=uv /uv /uvx /bin/
WORKDIR /workspace
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PYTHONPATH=/workspace/apps/api
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY scripts/download_embeddings.py /tmp/download_embeddings.py
ENV KNOWLEDGE_MODEL_PATH=/opt/bia/knowledge-model
RUN .venv/bin/python /tmp/download_embeddings.py
COPY apps/api ./apps/api
COPY scripts ./scripts
ENV PATH="/workspace/.venv/bin:$PATH"
RUN useradd --create-home app
USER app
EXPOSE 8000
CMD ["sh", "scripts/start-api.sh"]

FROM base AS test
USER root
RUN uv sync --frozen
USER app
CMD ["pytest"]

# The default Railway build must start the API, rather than the test stage.
FROM base AS production
