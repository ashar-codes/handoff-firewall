# Single-service production image: built React UI + FastAPI API + durable worker.
FROM node:24-alpine AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    UV_NO_DEV=1 UV_FROZEN=1 UV_PROJECT_ENVIRONMENT=/app/backend/.venv
RUN pip install --no-cache-dir uv==0.12.18
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project && rm -rf /root/.cache
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
COPY --from=frontend /src/dist /app/frontend/dist
COPY scripts/start-production.sh /app/start-production.sh
RUN useradd -m -u 10001 handoff && mkdir -p /app/data/files \
    && chown -R handoff:handoff /app/data && chmod 755 /app/start-production.sh
USER handoff
ENV PATH=/app/backend/.venv/bin:$PATH \
    APP_ENV=production COOKIE_SECURE=true \
    FRONTEND_DIST=/app/frontend/dist STORAGE_PATH=/app/data/files
EXPOSE 8000
CMD ["/app/start-production.sh"]
