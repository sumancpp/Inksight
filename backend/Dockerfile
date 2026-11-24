# ==========================================
# Inksight Backend Dockerfile
# Production-ready container for Render / Railway
# ==========================================

FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

# Install required Linux system packages for:
# - PaddleOCR / OpenCV: libgl1, libglib2.0-0, libgomp1
# - python-magic MIME detection: libmagic1
# - build essentials & curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first for optimal Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Ensure storage uploads directory exists
RUN mkdir -p /app/uploads

# Expose FastAPI service port
EXPOSE 8000

# Automatically run database migrations before starting the web server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
