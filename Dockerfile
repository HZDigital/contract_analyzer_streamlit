FROM node:22-bookworm-slim AS frontend-builder

WORKDIR /app/frontend

ARG VITE_MSAL_CLIENT_ID
ARG VITE_MSAL_AUTHORITY
ARG VITE_MSAL_REDIRECT_URI
ARG VITE_DEPLOYMENT_CONFIGURATION
ARG VITE_DEPLOYMENT_CSS
ENV VITE_MSAL_CLIENT_ID=${VITE_MSAL_CLIENT_ID} \
    VITE_MSAL_AUTHORITY=${VITE_MSAL_AUTHORITY} \
    VITE_MSAL_REDIRECT_URI=${VITE_MSAL_REDIRECT_URI} \
    VITE_DEPLOYMENT_CONFIGURATION=${VITE_DEPLOYMENT_CONFIGURATION} \
    VITE_DEPLOYMENT_CSS=${VITE_DEPLOYMENT_CSS}

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        poppler-utils \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --create-home app \
    && chown -R app:app /app

COPY --chown=app:app src/ ./src/
COPY --chown=app:app --from=frontend-builder /app/frontend/dist/ ./frontend/dist/

USER app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT', '8080'), timeout=3).read()"

CMD ["sh", "-c", "exec uvicorn src.api.main:app --host 0.0.0.0 --port \"${PORT:-8080}\""]
