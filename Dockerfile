FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8010

ARG PIP_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple

WORKDIR /app

RUN groupadd --system policy && useradd --system --gid policy --home-dir /app policy

COPY pyproject.toml ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY infra/__init__.py ./infra/__init__.py
COPY infra/bootstrap ./infra/bootstrap
COPY infra/search ./infra/search

RUN python -m pip install --disable-pip-version-check --index-url "$PIP_INDEX_URL" . && \
    mkdir -p /app/data/documents && \
    chown -R policy:policy /app

USER policy

EXPOSE 8010

CMD ["uvicorn", "policy_platform.api.app:app", "--host", "0.0.0.0", "--port", "8010", "--proxy-headers", "--forwarded-allow-ips", "*"]
