# syntax=docker/dockerfile:1.7

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app

RUN rm -f /etc/apt/apt.conf.d/docker-clean
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core

COPY jobs/excel_ingestion/requirements.txt ./requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY backend ./backend
COPY jobs/__init__.py ./jobs/__init__.py
COPY jobs/excel_ingestion/__init__.py \
     jobs/excel_ingestion/prefect_flow.py \
     ./jobs/excel_ingestion/
COPY prefect.yaml ./prefect.yaml
RUN mkdir -p \
    /app/data/runs \
    /app/data/cache \
    /app/data/source_files \
    /app/data/vector_db \
    /app/data/artifacts/embeddings \
    /app/data/artifacts/spreadsheets \
    && python -m compileall -q /app/backend /app/jobs

# Optional, deliberately non-default target for local BGE embeddings:
# docker build --target local-models ...
FROM base AS local-models
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    python -m pip install \
        --index-url https://download.pytorch.org/whl/cpu \
        "torch>=2.2.0,<3.0.0" \
    && python -m pip install "transformers>=4.44.0,<5.0.0"

# Prefect's Docker worker supplies the flow-run command. Keep the lean
# OpenAI-backed image as both the named deployment target and the default.
FROM base AS prefect-runtime
