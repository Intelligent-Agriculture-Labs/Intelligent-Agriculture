FROM python:3.13-slim
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml ./
COPY fieldshift ./fieldshift
RUN pip install --no-cache-dir .
COPY demo_cache ./demo_cache
ENV FIELDSHIFT_DEMO_DIR=/srv/demo_cache FIELDSHIFT_CACHE_DIR=/data/cache
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/health')"
CMD ["uvicorn", "fieldshift.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
