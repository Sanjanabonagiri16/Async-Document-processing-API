# Asynchronous Document Processing API

**Version 1.0.0** · **OpenAPI 3.1** (`GET {BASE_URL}/openapi.json`) · **Swagger UI** (`{BASE_URL}/docs`)

Backend to **submit** a document (file or URL), **process** it **asynchronously** via a worker queue, and **track** jobs with timestamps and a **mock JSON** result. Optional **webhooks** on completion.

### Base URL (`BASE_URL`)

Use **`BASE_URL`** as your API root **without a trailing slash** (all examples below).

| Where it runs | Example `BASE_URL` |
|---------------|--------------------|
| **Local Docker** (default) | `http://localhost:8000` |
| **Deployed / shared host** | `https://your-api.example.com` |

Set **`API_PUBLIC_BASE_URL`** to your public origin (same value as `BASE_URL` when deployed). It adds an entry under **Servers** in Swagger so **Try it out** can target that host first. Copy from [`.env.example`](./.env.example). With Docker Compose:

```bash
export API_PUBLIC_BASE_URL=https://your-api.example.com
docker compose up --build -d
```

Or add `API_PUBLIC_BASE_URL=...` to a `.env` file beside `docker-compose.yml`.

---

## Requirements coverage (assignment checklist)

### Functional requirements

| # | Requirement | How this project satisfies it |
|---|-------------|-------------------------------|
| 1 | API accepts **document file** or **file URL** and creates a processing job | `POST /v1/jobs` (JSON `document_url`, optional `webhook_url`) · `POST /v1/jobs/upload` (multipart `file`, optional `webhook_url`) |
| 2 | **Background** processing with **queue / worker** architecture | **Redis** (Celery broker + result backend) · **Celery** worker runs `process_document` tasks |
| 3 | **Simulate** processing (e.g. **10–20 s** delay) | `app/tasks.py`: `time.sleep(random.uniform(10.0, 20.0))` before writing mock `result` |
| 4 | Job states: **queued**, **processing**, **completed**, **failed** | `app/models.py` · `JobStatus` enum; worker transitions persisted in **PostgreSQL** |
| 5 | API to **fetch job status** with **timestamps** and **mock JSON result** | `GET /v1/jobs/{job_id}` returns `created_at`, `started_at`, `completed_at`, `result`, `error_message`, `retry_count` |
| 6 | Basic **retry** or **failure** handling | Celery `autoretry_for` + exponential backoff, max **3** retries; job marked `failed` when retries exhausted or on non-retryable errors · optional `SIMULATE_RANDOM_FAILURE_RATE` |
| 7 | **Multiple concurrent** processing jobs | Docker Compose worker: `celery ... --concurrency=4` · workers pull tasks from Redis in parallel |

### Technical expectations

| # | Expectation | Implementation |
|---|-------------|----------------|
| 1 | **FastAPI** (or Express) | **FastAPI** 0.115 |
| 2 | **Background workers / queues** (Celery, BullMQ, Redis, …) | **Celery 5** + **Redis** |
| 3 | **Clean structure** and **clear API** | `app/` package: `routers/`, `models`, `schemas`, `tasks`, `celery_app`, `config` · Versioned routes under `/v1/jobs` |
| 4 | **Logging** and **error handling** | `logging` in API + tasks; HTTP exceptions for validation/not-found; task failures persisted on `Job` |
| 5 | **README**: setup + architecture | This file |

### Bonus (optional) — all included

| Bonus | Implementation |
|-------|------------------|
| Docker | `Dockerfile` + `docker-compose.yml` (Postgres, Redis, **api**, **worker**) |
| Rate limiting | **SlowAPI** on create + read endpoints (`API_RATE_LIMIT`, `READ_RATE_LIMIT`) |
| Job listing API | `GET /v1/jobs` — `limit`, `offset`, optional `status` |
| Webhook on completion | If `webhook_url` set, worker **POST**s JSON after success (best-effort; failures logged only) |
| Database persistence | **PostgreSQL** + SQLAlchemy · `JSONB` for `result` |

---

## Architecture

```text
Client → FastAPI (api) → PostgreSQL (jobs)
              ↘ Redis (Celery broker/backend)
                   ↓
              Celery workers (concurrent)
                   ↓
              PostgreSQL (status + result) → optional HTTP webhook
```

| Component | Role |
|-----------|------|
| **api** | HTTP: create jobs, list, get status, `/health` |
| **worker** | Executes `process_document`; updates job rows |
| **postgres** | Durable jobs, list/filter, JSON results |
| **redis** | Task queue |

---

## Job states

| State | Meaning |
|-------|---------|
| `queued` | Accepted; waiting for a worker |
| `processing` | Worker is running the task |
| `completed` | Done; `result` populated |
| `failed` | Retries exhausted or non-retryable error; `error_message` set |

Processing is **simulated** (sleep + mock JSON), not real OCR/PDF parsing.

---

## API reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/jobs` | Create job from **URL** — JSON: `document_url`, optional `webhook_url` |
| `POST` | `/v1/jobs/upload` | Create job from **file** — multipart: `file`, optional `webhook_url` |
| `GET` | `/v1/jobs/{job_id}` | Job status, timestamps, `result` / `error_message` |
| `GET` | `/v1/jobs` | Paginated list: `limit`, `offset`, optional `status` |
| `GET` | `/health` | Liveness |

**Docs (open in browser, replace host):** `{BASE_URL}/docs` · `{BASE_URL}/redoc` · `{BASE_URL}/openapi.json`

**Rate limits** (per client IP): defaults `60/minute` on creates, `120/minute` on reads — configurable via env (see below).

---

## Quick start (Docker)

```bash
cd async-doc-processing
docker compose up --build -d
```

**Windows PowerShell:**

```powershell
.\scripts\start.ps1
```

- **API:** `{BASE_URL}` — local default `http://localhost:8000`  
- **Docs:** `{BASE_URL}/docs`

**Stop:** `docker compose down` · **Reset DB:** `docker compose down -v`

The **api** service has a **healthcheck** on `/health` (`docker compose ps` shows `healthy` when ready).

---

## Manual verification (smoke test)

Set `BASE_URL` (bash: `export BASE_URL=http://localhost:8000` · PowerShell: `$BASE_URL = "http://localhost:8000"`).

1. **GET** `{BASE_URL}/health` → `{"status":"ok"}`
2. **POST** `{BASE_URL}/v1/jobs` with body `{"document_url":"https://example.com/sample.pdf"}` → **202** + `id`
3. **GET** `{BASE_URL}/v1/jobs/{id}` until `status` is `completed` and `result` is present (~10–20 s)
4. **POST** `{BASE_URL}/v1/jobs/upload` with a real `file` → **202**; poll **GET** by `id` → `source_type: upload`
5. **GET** `{BASE_URL}/v1/jobs?limit=10` → `items`, `total`, pagination
6. `docker compose ps` → **api**, **worker**, **postgres**, **redis** all **Up**

---

## Example requests

Use the same `BASE_URL` as above (local: `http://localhost:8000`).

### URL job (curl — Windows `cmd`)

```bash
set BASE_URL=http://localhost:8000
curl -s -X POST %BASE_URL%/v1/jobs ^
  -H "Content-Type: application/json" ^
  -d "{\"document_url\": \"https://example.com/sample.pdf\", \"webhook_url\": \"https://webhook.site/your-id\"}"
```

### URL job (bash)

```bash
export BASE_URL=http://localhost:8000
curl -s -X POST "$BASE_URL/v1/jobs" \
  -H "Content-Type: application/json" \
  -d '{"document_url":"https://example.com/sample.pdf"}'
```

### URL job (PowerShell)

```powershell
$BASE_URL = "http://localhost:8000"
Invoke-RestMethod -Uri "$BASE_URL/v1/jobs" -Method Post -ContentType "application/json" `
  -Body '{"document_url":"https://example.com/sample.pdf","webhook_url":"https://webhook.site/your-id"}'
```

### File upload (PowerShell)

```powershell
$BASE_URL = "http://localhost:8000"
curl.exe -s -X POST "$BASE_URL/v1/jobs/upload" `
  -F "file=@.\path\to\document.pdf"
```

**Swagger tip:** For optional `webhook_url` on upload, either enter a real HTTPS URL or use **Send empty value**. Do not leave the placeholder text `string` — that value would be stored as the webhook URL.

### Poll status

```bash
curl -s "$BASE_URL/v1/jobs/<job-id>"
```

### List completed jobs

```bash
curl -s "$BASE_URL/v1/jobs?limit=10&status=completed"
```

---

## Local development (no full Docker for app)

1. **Python 3.12+**, **PostgreSQL**, **Redis** running locally (or run only `postgres` + `redis` via Compose).
2. Copy env: `cp .env.example .env` and set `DATABASE_URL`, `REDIS_URL`.
3. Install:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   ```

4. **Terminal A — API:** `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
5. **Terminal B — worker:** `celery -A app.celery_app worker --loglevel=info --concurrency=4`

Tables are created on API startup and when the Celery worker is ready.

---

## Configuration

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (SQLAlchemy) |
| `REDIS_URL` | Celery broker and result backend |
| `API_PUBLIC_BASE_URL` | Public API origin (no trailing slash); adds OpenAPI **Server** in `/docs` for the correct host |
| `API_RATE_LIMIT` | SlowAPI limit for `POST /v1/jobs` and `POST /v1/jobs/upload` |
| `READ_RATE_LIMIT` | SlowAPI limit for GET job endpoints |
| `SIMULATE_RANDOM_FAILURE_RATE` | `0.0`–`1.0` — random `RuntimeError` during processing to demo retries |

---

## Assumptions

- **File contents are not stored**; only **filename** or **URL string** is saved for the mock pipeline.
- **Processing** is **simulated** (delay + generated JSON), not real document analysis.
- **Webhook** targets should accept **POST** JSON within ~**15 s**; failed webhooks do not fail the job.

---

## Design decisions (short)

- **FastAPI + Celery + Redis** separates HTTP from long-running work and scales workers horizontally.
- **PostgreSQL + JSONB** keeps durable history and supports listing/filtering.
- **Two create routes** (`/v1/jobs` vs `/v1/jobs/upload`) give **clear OpenAPI** schemas in Swagger (JSON editor vs file picker).
- **Webhooks** are best-effort so **GET** remains the source of truth for status.
- **Rate limiting** reduces abuse on enqueue; job resources are not cached (status changes over time).
- **`API_PUBLIC_BASE_URL`** documents the reviewer-facing host in OpenAPI **Servers** without changing how Uvicorn binds (`0.0.0.0:8000` in Docker).

---

## Submission instructions

Per the assignment brief:

1. **Share your solution via a GitHub repository link** — push this project to GitHub and send the repo URL.
2. **Setup instructions and assumptions** — included in this README (**Quick start**, **Local development**, **Configuration**, **Assumptions**).
3. **Design decisions** — see **Design decisions (short)** above.
4. **Email** [**div@bpoptima.com**](mailto:div@bpoptima.com) with **CC** [**dj@bpoptima.com**](mailto:dj@bpoptima.com), including:
   - the **GitHub repository link**,
   - optional notes (e.g. deployed `BASE_URL` if reviewers should hit a live host, and that **`API_PUBLIC_BASE_URL`** is set for Swagger).

---

## Project layout

```text
async-doc-processing/
  app/
    main.py           # FastAPI app, DB init on lifespan
    config.py         # pydantic-settings
    database.py       # SQLAlchemy engine & sessions
    models.py         # Job ORM + JobStatus
    schemas.py        # Pydantic request/response models
    celery_app.py     # Celery app + worker DB init signal
    tasks.py          # process_document (delay, mock result, webhook)
    rate_limit.py     # SlowAPI limiter
    routers/jobs.py   # Job routes
  docker-compose.yml
  Dockerfile
  requirements.txt
  scripts/start.ps1
  .env.example
```
