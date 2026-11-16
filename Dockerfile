FROM python:3.12-alpine3.23@sha256:e0e17c55a255d32e515d3ae66577578f2a439ebe92cd4a8b69fc29421bbdba7d AS app-build
WORKDIR /app
ARG UV_CACHE_SCOPE=opspilot-full
ENV UV_HTTP_TIMEOUT=60 UV_CONCURRENT_DOWNLOADS=4
RUN apk --no-cache upgrade
RUN pip install --no-cache-dir uv==0.13.4
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,id=${UV_CACHE_SCOPE},target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,id=${UV_CACHE_SCOPE},target=/root/.cache/uv uv sync --frozen --no-dev --no-editable
COPY alembic.ini ./
COPY migrations ./migrations
RUN uv pip uninstall --system pip
RUN adduser -D -u 10001 opspilot
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1

FROM app-build AS runtime
RUN uv pip uninstall --system uv
USER opspilot
CMD ["python", "-m", "opspilot.api.main"]

FROM app-build AS tests
USER root
RUN --mount=type=cache,id=${UV_CACHE_SCOPE},target=/root/.cache/uv uv sync --frozen --no-editable
COPY tests ./tests
COPY docs/full/state-transitions.json ./docs/full/state-transitions.json
USER opspilot
CMD ["python", "-m", "pytest", "-p", "no:cacheprovider", "-q"]
