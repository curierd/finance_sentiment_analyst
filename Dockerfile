# ---- Build stage: install torch + heavy deps ----
FROM python:3.13-slim AS builder

RUN pip install --no-cache-dir --upgrade pip

# Install heavy deps in builder stage (cached layer)
RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu \
    numpy

# ---- Runtime stage ----
FROM python:3.13-slim AS runtime

LABEL org.opencontainers.image.title="Finance Sentiment Analyst"
LABEL org.opencontainers.image.description="金融评论情绪分析系统 — 多平台舆情评论采集、存储、分析"

# Create non-root user
RUN groupadd -r app && useradd -r -g app -d /app app

# Install runtime deps
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    flask>=3.0.0 \
    gunicorn \
    jieba \
    scikit-learn

# Copy torch + numpy from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages

# Create data directories
RUN mkdir -p /app/data /app/uploads && \
    chown -R app:app /app

# Copy application code
COPY --chown=app:app . /app
WORKDIR /app

# Remove dev/test files from image
RUN rm -rf /app/tests /app/.workbuddy /app/intermediate /app/.git

# Switch to non-root user
USER app

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DB_DRIVER=sqlite \
    DB_DSN=file:/app/data/comments.db?mode=rwc&cache=shared&timeout=30 \
    UPLOAD_DIR=/app/uploads \
    IMAGE_URL_PREFIX=/uploads

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import sqlite3; sqlite3.connect('/app/data/comments.db').execute('SELECT 1')" || exit 1

# Production entrypoint: init DB then start gunicorn
CMD python jobs/scripts/init_db.py && \
    gunicorn --bind 0.0.0.0:8000 --workers 2 --timeout 120 \
    --access-logfile - --error-logfile - \
    frontend.server:app
