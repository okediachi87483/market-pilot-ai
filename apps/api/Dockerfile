# syntax=docker/dockerfile:1

FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build

FROM base AS builder
COPY pyproject.toml ./
COPY app ./app
RUN pip install --prefix=/install .

FROM base AS runtime
RUN groupadd --gid 1000 marketpilot && \
    useradd --uid 1000 --gid marketpilot --shell /bin/bash --create-home marketpilot
COPY --from=builder /install /usr/local
WORKDIR /app
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh
USER marketpilot
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://localhost:8000/health/live', timeout=2).status == 200 else sys.exit(1)"
ENTRYPOINT ["./docker-entrypoint.sh"]
