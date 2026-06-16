FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.5.20 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
COPY src/ src/
RUN uv sync --frozen --no-dev --no-editable

RUN adduser --disabled-password --gecos "" appuser \
    && mkdir -p /app/Books \
    && chown -R appuser:appuser /app
USER appuser

VOLUME ["/app/Books"]

ENTRYPOINT ["uv", "run", "safari", "fetch"]
