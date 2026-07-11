FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    REMAP_SIGTERM=SIGQUIT

WORKDIR /app

RUN addgroup --system worker && adduser --system --ingroup worker worker

COPY services/worker/requirements-prod.lock /tmp/requirements-prod.lock
RUN python -m pip install --upgrade pip \
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

CMD ["celery", "-A", "cf_worker.celery_app:celery_app", "worker", "--beat", "--loglevel=INFO", "--queues=outbox.poll,outbox.process", "--concurrency=2"]
