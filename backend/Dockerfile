FROM python:3.12-slim
RUN pip install --no-cache-dir uv==0.12.18
WORKDIR /app
ENV UV_NO_DEV=1 UV_FROZEN=1
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
RUN useradd -m -u 10001 handoff && mkdir -p /data/files && chown -R handoff:handoff /data /app
USER handoff
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
