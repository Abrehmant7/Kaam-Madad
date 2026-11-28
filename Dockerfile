# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    PORT=10000

# The existing CNIC OCR provider invokes Tesseract locally (English data).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app backend/ ./
# Matches REPO_ROOT / "frontend" / "dist" in config/settings/base.py.
COPY --from=frontend-build --chown=app:app /app/frontend/dist /app/frontend/dist
RUN mkdir -p staticfiles private_media && chown -R app:app /app/backend
USER app

EXPOSE 10000

# Render Free has no pre-deploy command or shell. Initialize at runtime, with
# runtime secrets, and stop immediately if any initialization step fails.
# exec lets Gunicorn receive Render's shutdown signals directly.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py seed_catalog && python manage.py collectstatic --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 120 --access-logfile - --error-logfile -"]
