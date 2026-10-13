FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.10-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev
COPY amc/ ./amc/
COPY scripts/ ./scripts/
COPY config/ ./config/
ENTRYPOINT ["/app/.venv/bin/python", "-m", "amc"]
CMD ["--help"]
