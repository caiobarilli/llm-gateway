FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv

FROM python:3.13.18-slim@sha256:09a17cad02668ae61ece136b4fd36ac3849e14f670ebedb637ea3e15580525bc AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1

WORKDIR /app

FROM base AS dependencias

COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-install-project

FROM dependencias AS construcao

COPY src ./src

RUN uv sync --frozen --no-dev --no-editable

FROM dependencias AS teste

RUN uv sync --frozen --no-install-project

COPY src ./src
COPY tests ./tests
COPY tools ./tools
COPY docs/openapi.json ./docs/openapi.json

RUN uv sync --frozen

RUN uv run --frozen --no-sync ruff check . \
    && uv run --frozen --no-sync ruff format --check . \
    && uv run --frozen --no-sync python tools/sem_comentario.py \
    && uv run --frozen --no-sync mypy src tests tools \
    && uv run --frozen --no-sync pytest -q -p no:cacheprovider --cov=llm_gateway --cov-report=term-missing

FROM base

RUN python -m pip uninstall --yes --no-input pip \
    && groupadd --system --gid 10002 gateway \
    && useradd --system --uid 10002 --gid 10002 --no-create-home --shell /usr/sbin/nologin gateway

COPY --from=construcao /app/.venv /app/.venv

ENV PATH=/app/.venv/bin:$PATH

USER 10002

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

CMD ["uvicorn", "--factory", "llm_gateway.app:criar_app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-server-header"]
