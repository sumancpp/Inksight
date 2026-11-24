# Inksight Cloud Deployment Runbook

Complete step-by-step production deployment guide for **Inksight**:
- **Frontend**: [Vercel](https://vercel.com) (Vite React SPA)
- **Backend API**: [Render](https://render.com) or [Railway](https://railway.app) (FastAPI Docker Container)
- **Background Worker**: Render Celery Worker (Async OCR & AI Evaluation)
- **Database**: [Supabase](https://supabase.com) (Managed PostgreSQL)
- **Task Queue & Cache**: [Upstash](https://upstash.com) (Serverless Redis)
- **Object Storage**: [Cloudflare R2](https://www.cloudflare.com/developer-platform/r2/) or [AWS S3](https://aws.amazon.com/s3/)
- **AI Evaluation**: [Groq Cloud](https://groq.com) (OpenAI-compatible Llama 3.3 70B)

---

## Architecture Overview

```
                                      ┌────────────────────────────────┐
                                      │        User Browser            │
                                      └──────────────┬─────────────────┘
                                                     │ HTTPS (REST / Static)
                                                     ▼
                                      ┌────────────────────────────────┐
                                      │   Vercel: React Frontend SPA   │
                                      │    (https://inksight.vercel.app)│
                                      └──────────────┬─────────────────┘
                                                     │ CORS API Requests
                                                     ▼
                  ┌────────────────────────────────────────────────────────────────────────┐
                  │                             Render.com                                 │
                  │                                                                        │
                  │   ┌──────────────────────────────┐    ┌────────────────────────────┐   │
                  │   │  FastAPI Web Service         │    │  Celery Background Worker  │   │
                  │   │  (Docker: uvicorn)           │    │  (Docker: celery worker)   │   │
                  │   └──────────────┬───────────────┘    └─────────────┬──────────────┘   │
                  └──────────────────┼──────────────────────────────────┼──────────────────┘
                                     │                                  │
         ┌───────────────────────────┼──────────────────────────────────┼───────────────────────────┐
         │                           │                                  │                           │
         ▼                           ▼                                  ▼                           ▼
┌──────────────────┐       ┌──────────────────┐               ┌──────────────────┐        ┌──────────────────┐
│     Supabase     │       │     Upstash      │               │  Cloudflare R2   │        │    Groq Cloud    │
│  PostgreSQL DB   │       │   Redis Queue    │               │  Object Storage  │        │   Llama 3.3 70B  │
└──────────────────┘       └──────────────────┘               └──────────────────┘        └──────────────────┘
```

---

## Step 1: Provision Managed PostgreSQL on Supabase

1. Sign in to [Supabase](https://supabase.com) and click **New Project**.
2. Fill in the project details:
   - **Name**: `inksight-production`
   - **Database Password**: Generate and securely store a strong password.
   - **Region**: Choose a region close to your Render deployment (e.g., `US East (N. Virginia)` / `us-east-1`).
3. Once the database is provisioned, go to **Project Settings** > **Database**.
4. In the **Connection string** section:
   - Select **URI**.
   - Choose the **Connection Pooling** mode (recommended port: `6543` in `session` mode for migrations, or `transaction` mode for API traffic).
   - Your connection string will look like:
     ```
     postgresql://postgres.[YOUR-PROJECT-REF]:[YOUR-PASSWORD]@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require
     ```
   - Note: Inksight automatically converts `postgres://` or `postgresql://` to `postgresql+psycopg2://` at runtime.

---

## Step 2: Provision Cloud Redis on Upstash

1. Sign in to [Upstash Console](https://console.upstash.com/).
2. Click **Create Database**:
   - **Name**: `inksight-redis`
   - **Type**: Serverless (Standard)
   - **Region**: Choose the same cloud region (e.g., `us-east-1`).
   - **TLS (SSL)**: **Enabled** (Required for security).
   - **Eviction**: No eviction (or volatile-lru).
3. Under the database details, scroll to **REST / Redis API** and copy the **`rediss://`** connection URL:
   ```
   rediss://default:[YOUR-UPSTASH-PASSWORD]@[YOUR-UPSTASH-ENDPOINT].upstash.io:6379
   ```
   *(Note the double `s` in `rediss://` which enables TLS encryption for Celery).*

---

## Step 3: Provision S3 / Cloudflare R2 Object Storage

Cloudflare R2 provides S3-compatible storage with zero egress fees:

1. In [Cloudflare Dashboard](https://dash.cloudflare.com/), navigate to **R2**.
2. Click **Create Bucket** and name it `inksight-uploads`.
3. In **R2 Account Details**, click **Manage R2 API Tokens** > **Create API Token**:
   - **Permissions**: Object Read & Write.
   - **TTL**: Forever (or as needed).
4. Save the generated credentials:
   - `Access Key ID`
   - `Secret Access Key`
   - `Endpoint URL`: `https://<account_id>.r2.cloudflarestorage.com`
5. *(Optional: CORS)* In bucket **Settings** > **CORS Policy**, add:
   ```json
   [
     {
       "AllowedOrigins": ["https://inksight.vercel.app", "http://localhost:5173"],
       "AllowedMethods": ["GET", "PUT", "POST", "HEAD"],
       "AllowedHeaders": ["*"]
     }
   ]
   ```

---

## Step 4: Run Database Migrations on the Cloud Database

Before starting the web services, execute Alembic migrations and seed the initial teacher account:

### 1. Run Migrations from Local Terminal
```bash
cd backend

# Set the cloud database URL
export DATABASE_URL="postgresql+psycopg2://postgres.[REF]:[PASSWORD]@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require"

# Run all migrations up to head
.venv/bin/alembic upgrade head
```

### 2. Seed Initial Demo Teacher & Assessment Data
```bash
# Seed default teacher (smith@learngraph.edu / teacher123) and sample data
.venv/bin/python scripts/seed_cluster_demo.py --force
```

---

## Step 5: Deploy Backend Services to Render

### Option A: Automated Blueprint Deployment (Recommended)
This repository includes a `render.yaml` Blueprint file at the repository root.

1. Connect your GitHub repository to [Render](https://dashboard.render.com).
2. In the Render Dashboard, click **New +** > **Blueprint**.
3. Select your repository. Render will automatically parse `render.yaml` and discover two services:
   - **`inksight-backend`** (Web Service, Docker)
   - **`inksight-celery-worker`** (Background Worker, Docker)
4. Fill in the requested secret environment variables:
   - `DATABASE_URL`: Your Supabase PostgreSQL connection string.
   - `REDIS_URL`: Your Upstash Redis TLS connection string (`rediss://...`).
   - `CELERY_BROKER_URL`: Same as `REDIS_URL`.
   - `CELERY_RESULT_BACKEND`: Same as `REDIS_URL`.
   - `VLLM_API_KEY`: Your Groq API key (`gsk_...`).
   - `AWS_ACCESS_KEY_ID`: Cloudflare R2 / AWS S3 Access Key.
   - `AWS_SECRET_ACCESS_KEY`: Cloudflare R2 / AWS S3 Secret Key.
   - `S3_BUCKET_NAME`: `inksight-uploads`
   - `S3_ENDPOINT_URL`: `https://<account_id>.r2.cloudflarestorage.com`
5. Click **Apply**. Render will build the Docker container and deploy both services.

### Option B: Manual Web Service Deployment
1. Click **New +** > **Web Service**.
2. Select your repository, choose **Docker** runtime:
   - **Docker Context**: `./backend`
   - **Docker Command**: Leave default (runs `CMD` from Dockerfile).
   - **Health Check Path**: `/api/v1/health`
3. Add the environment variables specified in `backend/.env.example`.
4. Create a second service: **New +** > **Background Worker**:
   - **Runtime**: Docker
   - **Docker Context**: `./backend`
   - **Start Command**: `celery -A app.core.celery_app worker --loglevel=info --concurrency=2`
   - Attach the same environment variables.

---

## Step 6: Deploy Frontend to Vercel

1. Log in to [Vercel](https://vercel.com) and click **Add New** > **Project**.
2. Import your GitHub repository.
3. Configure project settings:
   - **Framework Preset**: `Vite`
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
4. In **Environment Variables**, add:
   - `VITE_API_BASE_URL`: `https://inksight-backend.onrender.com/api/v1`
   - `VITE_DEMO_MODE`: `false` (or `true` if you wish to retain auto-login for evaluation judges).
5. Click **Deploy**.
6. The `frontend/vercel.json` file ensures that all React Router routes (`/dashboard`, `/review`, `/clusters`) rewrite cleanly to `/index.html` without 404 errors on browser refresh.

---

## Step 7: Update CORS in Backend

Once your Vercel deployment completes, update the `BACKEND_CORS_ORIGINS` environment variable in your Render Web Service to include your live Vercel domain:

```env
BACKEND_CORS_ORIGINS=https://inksight.vercel.app,https://inksight-frontend.vercel.app,http://localhost:5173
```

Render will automatically trigger a zero-downtime redeploy.

---

## Step 8: Post-Deployment Smoke Test & Verification

Test your live cloud deployment with the following checks:

### 1. Test Backend Health Check
```bash
curl -s https://inksight-backend.onrender.com/api/v1/health
```
**Expected response**:
```json
{
  "status": "ok",
  "app_name": "Inksight",
  "version": "0.1.0",
  "environment": "production",
  "api_version": "v1"
}
```

### 2. Test AI Evaluator Health Check
```bash
curl -s https://inksight-backend.onrender.com/api/v1/health/ai
```
**Expected response**:
```json
{
  "status": "online",
  "provider": "vllm",
  "model": "llama-3.3-70b-versatile",
  "error": null
}
```

### 3. Verify Frontend SPA
1. Open `https://inksight.vercel.app` in your browser.
2. Verify the dynamic AI status indicator shows `● AI Engine: Online` (green).
3. Navigate to `/review` and refresh the page (verifying `vercel.json` rewrites).
4. Perform a sample student document upload to verify the end-to-end flow:
   `Upload` ➔ `Storage (S3/R2)` ➔ `Background Worker (Celery/Redis)` ➔ `Diagnostic AI (Groq)` ➔ `UI Findings Display`.

---

## Troubleshooting Guide

| Issue | Cause | Resolution |
| :--- | :--- | :--- |
| **`404 Not Found` on page refresh** | SPA router redirect missing on Vercel | Verify `frontend/vercel.json` exists with rewrite `{"source": "/(.*)", "destination": "/index.html"}`. |
| **CORS error in browser console** | `BACKEND_CORS_ORIGINS` doesn't match frontend domain | Add the exact Vercel URL (including `https://`) to `BACKEND_CORS_ORIGINS` in Render. |
| **`Prepared statement already exists` (Supabase)** | Session vs Transaction pooler mismatch | Append `?sslmode=require` and connect via port `6543` in session pooler mode for Alembic. |
| **Celery worker cannot connect to Redis** | Missing TLS protocol in Redis URL | Ensure the Upstash connection string uses **`rediss://`** (with two `s`'s) rather than `redis://`. |
| **`HTTP 502 / Bad Gateway` on file upload** | Render request timeout during long processing | Ensure Celery async task queue is active (`CELERY_TASK_ALWAYS_EAGER=false`) so upload returns `202 Accepted` immediately. |
| **AI Engine displays Offline** | Invalid or expired Groq API key | Update `VLLM_API_KEY` in Render environment variables; check `/api/v1/health/ai` for error message. |
