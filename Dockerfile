FROM python:3.14-slim-bookworm AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright CLOUD_INTEL_DB=/app/data/cloud_intel.db

COPY requirements.txt ./
# Playwright's bundled Node needs libatomic before it can install Chromium.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libatomic1 \
    && pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home app \
    && install -d -o app -g app /app/data /app/evidence

COPY app ./app
COPY collectors ./collectors
COPY comparison ./comparison
COPY config ./config
COPY datasets ./datasets
COPY extractors ./extractors
COPY normalization ./normalization
COPY scripts ./scripts
COPY storage ./storage
COPY util ./util

USER app
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS test
USER root
COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY --chown=app:app conftest.py pytest.ini ./
COPY --chown=app:app tests ./tests
RUN chown app:app /app
USER app

FROM runtime AS production
