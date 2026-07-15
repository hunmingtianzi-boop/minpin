FROM python:3.13.14-slim-trixie AS runtime

ARG PIP_VERSION=26.1.2
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    FASTEMBED_CACHE_PATH=/models

WORKDIR /app

RUN addgroup --system embedding \
    && adduser --system --ingroup embedding embedding \
    && mkdir -p /models \
    && chown embedding:embedding /models

COPY services/embedding/requirements.lock ./requirements.lock
RUN python -m pip install --upgrade "pip==${PIP_VERSION}" \
    && python -m pip install --requirement requirements.lock

COPY services/embedding/app.py ./app.py

USER embedding
EXPOSE 8010

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]
