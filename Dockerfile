FROM python:3.13-slim

WORKDIR /app

# Install uv for faster dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files and lockfile for reproducible installs
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project

COPY . .

# Create data directory
RUN mkdir -p data/memory/users/default

EXPOSE 8080

CMD ["uv", "run", "python", "-m", "core.main"]
