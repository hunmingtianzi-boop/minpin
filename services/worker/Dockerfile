FROM python:3.14.6-slim-trixie AS runtime

ARG PIP_VERSION=26.1.2
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    REMAP_SIGTERM=SIGQUIT

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
        libsm6 \
        libxext6 \
        libxcb1 \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system worker && adduser --system --ingroup worker worker

COPY services/worker/requirements-prod.lock /tmp/requirements-prod.lock
RUN python -m pip install --upgrade "pip==${PIP_VERSION}" \
    && python -m pip install --requirement /tmp/requirements-prod.lock

COPY services/api/pyproject.toml /src/api/pyproject.toml
COPY services/api/app /src/api/app
RUN python -m pip install --no-deps /src/api

COPY services/worker/pyproject.toml /src/worker/pyproject.toml
COPY services/worker/cf_worker /src/worker/cf_worker
RUN python -m pip install --no-deps /src/worker

COPY packages/evals /eval-data

USER worker
EXPOSE 8020

CMD ["celery", "-A", "cf_worker.celery_app:celery_app", "worker", "--beat", "--schedule=/tmp/celerybeat-schedule", "--loglevel=INFO", "--queues=outbox.poll,outbox.process", "--concurrency=1"]
