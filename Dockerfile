FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS runtime
WORKDIR /app
RUN pip install --no-cache-dir uv==0.13.1
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-editable
COPY alembic.ini ./
COPY migrations ./migrations
RUN useradd --create-home --uid 10001 opspilot
USER opspilot
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
CMD ["python", "-m", "opspilot.api.main"]

FROM runtime AS tests
USER root
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-editable
COPY tests ./tests
USER opspilot
CMD ["python", "-m", "pytest", "-p", "no:cacheprovider", "-q"]
