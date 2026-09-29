
# ============================================================
# CP2 — Production-ready Dockerfile
# ============================================================

# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app

# Tạo virtual environment
RUN python -m venv /opt/venv

# Sử dụng Python và pip từ virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements trước để tận dụng Docker cache
COPY requirements.txt .

# Cài đặt dependencies
RUN pip install --no-cache-dir -r requirements.txt


# ============================================================
# Stage 2: Runtime
# ============================================================

FROM python:3.11-slim AS runtime

WORKDIR /app

# Thiết lập biến môi trường
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

# Copy virtual environment từ builder
COPY --from=builder /opt/venv /opt/venv

# Copy source code
COPY app/ ./app/
COPY utils/ ./utils/

# Tạo user thường, không chạy bằng root
RUN groupadd --system appgroup \
    && useradd --system --gid appgroup --create-home appuser \
    && chown -R appuser:appgroup /app

USER appuser

# Document default port
EXPOSE 8000

# Healthcheck — không cần cài thêm curl
HEALTHCHECK --interval=30s \
    --timeout=5s \
    --start-period=10s \
    --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/health', timeout=3)" || exit 1

# Chạy Uvicorn, đọc PORT từ environment
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
