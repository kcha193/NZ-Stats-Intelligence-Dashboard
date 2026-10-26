# syntax=docker/dockerfile:1
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TZ=Pacific/Auckland \
    NZSTATS_DATA_DIR=/data NZSTATS_STATIC_DIR=/app/static \
    NZSTATS_SOURCES_FILE=/app/config/sources.toml \
    NZSTATS_RESEARCH_SOURCES_FILE=/app/config/research_sources.toml
WORKDIR /app
COPY backend/pyproject.toml backend/
COPY backend/src backend/src
RUN pip install './backend[research]'
COPY config /app/config
COPY --from=web /web/dist /app/static
RUN useradd --system --uid 10001 nzstats && mkdir /data && chown nzstats /data
USER nzstats
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
CMD ["nzstats", "serve", "--host", "0.0.0.0", "--port", "8000"]
