# Inksight — AI Learning Diagnostic Platform

Inksight is an AI-powered diagnostic assessment and targeted misconception remediation platform for student exams and handwritten answer sheets.

## Core Capabilities
- **Zero Question Paper Mode**: Upload handwritten student answer sheets directly without a pre-configured question paper. Inksight automatically segments work, infers questions, evaluates answers, and flags misconceptions.
- **Handwriting OCR**: High-accuracy document parsing with PaddleOCR and clean deduplication.
- **Diagnostic Evaluation**: Evidence-grounded rubrics powered by LLM evaluators with circular confidence scoring.
- **Formative Practice & Remediation**: AI-generated targeted follow-up questions and adaptive remediation items with strict teacher verification gates.

## Architecture
- **Frontend**: React 18, TypeScript, Vite, CSS design tokens.
- **Backend**: FastAPI, SQLAlchemy, SQLite/PostgreSQL, Pydantic v2.
- **Background Worker**: Celery + Redis for asynchronous OCR extraction and AI diagnostic evaluation.

## Background Worker & Async Queue (Celery + Redis)

Inksight uses Celery with a Redis broker to execute compute-intensive OCR extraction and AI diagnostic evaluations in the background without blocking FastAPI API threads.

### 1. Start Redis
Start Redis locally or via Docker:
```bash
# Via Docker
docker run -d --name inksight-redis -p 6379:6379 redis:alpine

# Or via local system service
redis-server
```

### 2. Configure Environment Variables
Set the broker and result backend in `backend/.env`:
```ini
CELERY_BROKER_URL="redis://localhost:6379/0"
CELERY_RESULT_BACKEND="redis://localhost:6379/0"
CELERY_TASK_ALWAYS_EAGER=false
```

### 3. Start the Celery Worker
In the `backend` directory, run:
```bash
celery -A app.core.celery_app worker --loglevel=info
```
*(In automated test and zero-dependency offline environments, set `CELERY_TASK_ALWAYS_EAGER=true` to execute tasks synchronously in-memory).*
