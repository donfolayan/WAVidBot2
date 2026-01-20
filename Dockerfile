# Use official Python runtime as parent image
FROM python:3.12-slim-bullseye

# Install system dependencies including ffmpeg
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install uv for dependency management
RUN pip install --no-cache-dir uv

# Copy project metadata files and source code (needed for build)
COPY pyproject.toml README.md ./
COPY src ./src

# Install Python dependencies using uv sync
RUN uv sync --no-dev

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY . .

# Create downloads directory
RUN mkdir -p downloads

# Set environment variable for ffmpeg
ENV FFMPEG_PATH=ffmpeg
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Health check - verify app is responding
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application with uv run (automatically uses the venv)
CMD ["uv", "run", "gunicorn", "src.wabotii.__main__:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120"]
