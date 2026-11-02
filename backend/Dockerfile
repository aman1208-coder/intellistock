FROM python:3.12-slim AS dependency-builder

WORKDIR /build
COPY backend/requirements.txt ./requirements.txt
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend:/app

WORKDIR /app
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app app
COPY --from=dependency-builder /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels /wheels/* \
    && rm -rf /wheels
COPY --chown=app:app backend/app /app/backend/app
COPY --chown=app:app backend/scripts /app/backend/scripts
COPY --chown=app:app ml_models /app/ml_models

USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]