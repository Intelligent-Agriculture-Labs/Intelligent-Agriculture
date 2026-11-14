# FieldShift: one image serving the API (/api, /docs) and the web app (/).
# Stage 1 builds the Expo web bundle; stage 2 is the Python API that also serves the static files.
FROM node:22-alpine AS web
WORKDIR /app
COPY app/package.json app/package-lock.json ./
RUN npm config set fetch-retries 6 && npm config set fetch-retry-mintimeout 20000 && npm config set fetch-retry-maxtimeout 180000 && npm config set maxsockets 4 \
 && npm ci --no-audit --no-fund
COPY app/ ./
RUN npx expo export -p web --output-dir dist

FROM python:3.13-slim
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY backend/pyproject.toml ./
COPY backend/fieldshift ./fieldshift
RUN pip install --no-cache-dir .
COPY backend/demo_cache ./demo_cache
COPY --from=web /app/dist ./web
ENV FIELDSHIFT_DEMO_DIR=/srv/demo_cache FIELDSHIFT_CACHE_DIR=/data/cache FIELDSHIFT_WEB_DIR=/srv/web
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/health')"
CMD ["uvicorn", "fieldshift.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
