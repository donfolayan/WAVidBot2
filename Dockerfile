# Use official Python runtime as parent image
FROM python:3.12-slim-bookworm

# Install system dependencies including ffmpeg
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install uv for dependency management
RUN pip install --no-cache-dir uv

# Copy project metadata files and source code (needed for build)
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Install Python dependencies using the committed lockfile
RUN uv sync --locked --no-dev

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copy remaining application files (legal pages, etc.)
COPY legal ./legal

# Create downloads directory (required for StaticFiles mount at startup)
RUN mkdir -p downloads

# Set environment variable for ffmpeg
ENV FFMPEG_PATH=ffmpeg
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Health check - verify app is responding without cascading to WAHA
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", \"8000\")}/live', timeout=3).read()" || exit 1

# Run application from the prebuilt virtualenv and bind Railway's dynamic port.
CMD ["sh", "-c", "gunicorn src.wabotii.__main__:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000} --workers 1 --timeout 120"]
