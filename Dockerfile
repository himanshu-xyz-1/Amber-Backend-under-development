# ── Stage 1: Build & Dependencies ──
FROM python:3.10-slim as builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ── Stage 2: Runtime Production Image ──
FROM python:3.10-slim as runtime

WORKDIR /app

# Security: create unprivileged system user
RUN groupadd -g 10001 amber && \
    useradd -u 10000 -g amber -s /bin/bash -m amber

# Copy installed python packages from builder
COPY --from=builder /root/.local /home/amber/.local

# Set path for user installed packages
ENV PATH=/home/amber/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy application source code and migrations
COPY --chown=amber:amber backend /app/backend
COPY --chown=amber:amber data /app/data
COPY --chown=amber:amber alembic /app/alembic
COPY --chown=amber:amber alembic.ini /app/alembic.ini

USER amber

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health/liveness')" || exit 1

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
