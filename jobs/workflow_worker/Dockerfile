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
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r appuser -g 1000 \
    && useradd -r -u 1000 -g appuser appuser

COPY jobs/workflow_worker/requirements.txt ./requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY backend ./backend
COPY modules ./modules
COPY jobs/__init__.py ./jobs/__init__.py
COPY jobs/workflow_worker ./jobs/workflow_worker
RUN mkdir -p \
    /app/data/runs \
    /app/data/cache \
    /app/data/source_files \
    /app/data/vector_db \
    /app/data/artifacts/embeddings \
    /app/data/artifacts/spreadsheets \
    && python -m compileall -q /app/backend /app/modules /app/jobs \
    && chown -R appuser:appuser /app/data

USER appuser

ENTRYPOINT ["python", "-m", "jobs.workflow_worker.main"]

# Optional CPU-only local embedding target. The default OpenAI-backed image is
# deliberately lean so cold starts and k3d imports stay fast.
FROM base AS local-models
USER root
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    python -m pip install \
        --index-url https://download.pytorch.org/whl/cpu \
        "torch>=2.2.0,<3.0.0" \
    && python -m pip install "transformers>=4.44.0,<5.0.0"
USER appuser

FROM base AS runtime
