# DocFormatter AI

Turn raw, messy text into well-structured documents with a **local LLM** (Ollama `gpt-oss:20b`).
Paste text or upload a file, pick a format (business report, meeting minutes, resume, …), watch the
result stream in, edit it, and export to **DOCX, PDF, HTML or Markdown**. Every run is stored in PostgreSQL.

**Stack:** React 19 + Vite + Tailwind · FastAPI (async) · PostgreSQL 17 + Alembic · Ollama · nginx

## Features

- **Background jobs**: formatting continues if the browser closes or the network drops. The UI reconnects automatically, and opening a running document re-attaches to its live progress.
- **GPU-aware queue**: by default one document is formatted at a time and the rest wait in line with live position updates. The queue has a size limit, and requests beyond it get HTTP 429.
- **Cancel** running or queued jobs. If a re-format fails or is cancelled, the previous good result is kept.
- **13 built-in templates**, including Letterhead and Contract / Agreement (updated automatically on upgrade), plus custom templates.
- **File upload**: PDF, DOCX, TXT, MD, HTML, CSV, JSON, YAML, RST.
- **Long documents** are split on paragraph boundaries. Later parts receive the outline written so far, so the structure continues instead of restarting.
- **Edit** the Markdown, **export** it to Word, PDF, HTML or Markdown, and **search** your history. Documents have deep links (`/#/doc/12`).
- **Dark mode**: choose Light, Dark or System in the sidebar footer. System follows the OS setting and updates live. Your choice is saved in the browser and applied before first paint, so the page never flashes the wrong theme. Exported files always stay light, since they are meant for printing and sharing.

## Running in production (Docker)

```bash
cp .env.example .env          # set POSTGRES_PASSWORD (URL-safe), OLLAMA_URL, etc.
docker compose up -d --build
```

Open `http://<host>:8080`. On startup:

1. `db` starts, and its health check gates the API.
2. `api` applies Alembic migrations (`RUN_MIGRATIONS=true` by default), seeds the built-in templates, marks any jobs interrupted by a previous restart as failed, and starts serving.
3. `web` (unprivileged nginx) serves the UI and proxies `/api` with streaming enabled.

| Concern | How it's handled |
|---|---|
| Processes | API and nginx run as non-root users; every service has a Docker health check |
| Network | Postgres is not published. Only the web port is exposed (`HTTP_BIND`/`HTTP_PORT`) |
| Headers | CSP, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`. Exported HTML is served with `CSP: sandbox` |
| Caching | Hashed assets are immutable for one year; `index.html` is `no-cache`; responses are gzipped |
| Logging | JSON logs with a request ID (from nginx `$request_id`) that also follows background job logs. Docker log rotation is 10 MB × 5 |
| Errors | Unhandled errors return `{"detail": "Internal server error", "request_id": …}` without stack traces |
| Shutdown | Graceful 20 s drain. Jobs interrupted by a restart are marked *failed* with a clear message |
| API docs | `/docs` and `/openapi.json` are disabled when `ENVIRONMENT=production` |

**TLS**: put a TLS-terminating reverse proxy (Caddy, Traefik, nginx, or a load balancer) in front, and set `HTTP_BIND=127.0.0.1` if it runs on the same host.

**Access control**: there are no logins by design. Expose the app only on a trusted network, or add authentication at the reverse proxy (e.g. basic auth, OAuth2-proxy, or a VPN).

**Scaling**: the API runs **one worker** on purpose, because the job queue and live event fan-out live in that process. The LLM GPU is the bottleneck anyway. `MAX_CONCURRENT_JOBS` controls how many jobs hit Ollama at once. Running several API replicas would require moving the queue to an external broker such as Redis.

### Backups

```bash
# Backup
docker compose exec -T db pg_dump -U docformatter -Fc docformatter > backup-$(date +%F).dump
# Restore into an empty database
docker compose exec -T db pg_restore -U docformatter -d docformatter --clean --if-exists < backup-2026-11-24.dump
```

### Upgrading

```bash
git pull && docker compose up -d --build   # migrations run automatically on api start
```

## Local development

Prerequisites: Python 3.12, Node 20+, Docker, and access to the Ollama server.

```powershell
# 1. Dev database on 127.0.0.1:5434
docker compose -f compose.dev.yml up -d

# 2. API on http://127.0.0.1:8100 (interactive docs at /docs)
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements-dev.txt
copy .env.example .env
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8100 --reload

# 3. UI on http://localhost:5180 (proxies /api to the API), in a second terminal
cd frontend
npm install
npm run dev
```

> On Windows, use `127.0.0.1` rather than `localhost` in `DATABASE_URL`. `localhost` resolves to IPv6 first, which adds about 2 seconds to every new database connection.

### Tests, linting and migrations

```powershell
cd backend
.\.venv\Scripts\pytest -q                 # 40 tests; uses the docformatter_test DB and a fake LLM
.\.venv\Scripts\ruff check app tests alembic
.\.venv\Scripts\ruff format app tests alembic
.\.venv\Scripts\alembic revision --autogenerate -m "describe change"   # after changing models.py
.\.venv\Scripts\alembic check             # fails if models and migrations have drifted
cd ..\frontend; npm run build             # type-check + bundle
```

The tests never call the real Ollama server. They create the `docformatter_test` database if it is missing, run migrations down and up, and cover the job lifecycle (queueing, cancellation, reconnect replay, failure handling, chunking), the API, extraction and the exporters. Set `TEST_DATABASE_URL` to point them elsewhere. CI (`.github/workflows/ci.yml`) runs lint, a migration drift check, tests, the frontend build and the Docker image builds.

## Configuration

API settings come from environment variables (or `backend/.env` in development):

| Variable | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` enables JSON logs and disables the API docs |
| `DATABASE_URL` | `postgresql+asyncpg://…@127.0.0.1:5434/docformatter` | Async SQLAlchemy URL |
| `OLLAMA_URL` / `OLLAMA_MODEL` | `http://192.168.0.84:11434` / `gpt-oss:20b` | LLM server and model |
| `OLLAMA_TIMEOUT` | `600` | Seconds to wait between streamed tokens |
| `MAX_CONCURRENT_JOBS` | `1` | Jobs sent to the LLM at once |
| `MAX_QUEUED_JOBS` | `20` | Running + waiting jobs before HTTP 429 |
| `CHUNK_CHARS` | `24000` | Documents longer than this are formatted in parts |
| `MAX_INPUT_CHARS` / `MAX_UPLOAD_MB` | `300000` / `20` | Input limits |
| `LOG_LEVEL` / `LOG_JSON` | `INFO` / auto | Logging |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `10` / `10` | Connection pool |
| `CORS_ORIGINS` | dev origins | Only needed when the UI is served from another origin |
| `RUN_MIGRATIONS` | `true` | Container entrypoint runs `alembic upgrade head` |

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/jobs` | Queue a formatting job, which returns `202 {document_id, status, queue_position}` |
| GET | `/api/jobs/{id}/events` | NDJSON stream: `snapshot`, then `queued`/`status`/`chunk`/`thinking`/`content`/`ping`, then `done` \| `error` \| `cancelled` |
| POST | `/api/jobs/{id}/cancel` | Cancel a running or queued job |
| GET | `/api/jobs/stats` | Running and queued job counts |
| POST | `/api/extract` | Upload a file and get plain text back |
| GET | `/api/documents?q=&limit=&offset=` | History, with search |
| GET/PUT/DELETE | `/api/documents/{id}` | Read, edit (title or markdown), delete (cancels any running job) |
| GET | `/api/documents/{id}/export?format=md\|html\|docx\|pdf` | Download |
| GET/POST | `/api/templates` · PUT/DELETE `/api/templates/{id}` | Templates (built-ins are read-only) |
| GET | `/api/health/live` · `/api/health/ready` · `/api/health` | Liveness, readiness (database), full status |

## Project layout

```
docker-compose.yml        production stack (db, api, web)
compose.dev.yml           dev database only
backend/
  app/main.py             app factory, lifespan (seed, recover, start queue)
  app/jobs.py             background job manager: queue, cancel, event fan-out
  app/middleware.py       request IDs, access log, safe 500s, security headers
  app/routers/            jobs, documents, templates, extract, health
  app/services/           llm (Ollama client, chunking), prompts, export, extract
  alembic/                migrations
  tests/                  pytest suite (fake LLM, real Postgres)
frontend/
  src/App.tsx             state, job following with auto-reconnect
  src/components/         Sidebar, InputPanel, OutputPanel, TemplatesView, ErrorBoundary
  nginx.conf              production proxy + caching + security headers
```

## Known limitations

- Scanned PDFs have no text layer and are rejected (no OCR).
- PDF export uses DejaVu Sans in Docker (Arial on Windows). CJK characters and emoji are missing from those fonts, so use DOCX or HTML export for that content.
- There are no user accounts; anyone who can reach the app can see all documents.
