# Deployment environment variables

**Classes:**
- **Secret:** required production secret. Set only in Render; never commit or share it.
- **Required:** required production non-secret.
- **Optional:** has a safe default.
- **Dev only:** development only.

Settings are read from environment variables (and `backend/.env` locally). Unsafe production combinations stop the service at start-up.

## Application and security

| Variable | Class | Production value / notes |
|---|---|---|
| `APP_ENV` | Required | `production`. Enables the strict checks below, disables the API docs UI, forbids the sample seed and the test model. Preset by the image and Blueprint. |
| `COOKIE_SECURE` | Required | `true`. Production refuses `false`. Preset. |
| `FRONTEND_ORIGIN` | Required | The exact public HTTPS origin, e.g. `https://handoff-firewall.onrender.com` (no path, no trailing slash). If empty on Render, the start script uses `RENDER_EXTERNAL_URL`. Used for the Origin check and CORS; never a wildcard. Production refuses non-`https://` values. |
| `FRONTEND_DIST` | Optional | Built UI directory served at `/`. Preset in the image (`/app/frontend/dist`); unset in development, where Vite serves the UI. The service fails to start if it's set but has no `index.html`. |
| `SESSION_HOURS` | Optional | Session lifetime, 1–24 hours; default 8. |
| `UPLOAD_LIMIT` | Optional | Bytes per upload; default 10 MiB. |
| `PORT` | Optional | Set by Render; the API binds `0.0.0.0:$PORT`. Default 8000. |

## Database

| Variable | Class | Production value / notes |
|---|---|---|
| `DATABASE_URL` | Secret | Supabase **Session pooler** URI (port 5432) with `?sslmode=require`. A plain `postgresql://` URI is accepted and converted for the psycopg driver. Production refuses non-PostgreSQL URLs. |
| `MIGRATION_DATABASE_URL` | Optional (secret if set) | Separate connection for migrations. Defaults to `DATABASE_URL`. |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | Optional | Per-process pool; the Blueprint sets `3` / `2`, so the API and worker together stay within the free Session-pooler budget. Defaults are 5 / 10. |

## Evidence storage

| Variable | Class | Production value / notes |
|---|---|---|
| `STORAGE_PROVIDER` | Required | `supabase` (the Blueprint default). `local` is for development and tests; on Render's free tier local files are lost on restart. |
| `SUPABASE_URL` | Required | `https://<project-ref>.supabase.co`. Must be `https://`. |
| `SUPABASE_SERVICE_ROLE_KEY` | Secret | Supabase secret key (`sb_secret_…`, sent as `apikey`) or legacy `service_role` JWT (also sent as `Bearer`). Backend only; bypasses Row Level Security. Required when `STORAGE_PROVIDER=supabase`. |
| `SUPABASE_STORAGE_BUCKET` | Optional | Private bucket name; default `handoff-evidence`. Lowercase letters, digits, `-` and `_` only. |
| `STORAGE_TIMEOUT` | Optional | Seconds per storage request, 1–60; default 20. |
| `STORAGE_PATH` | Dev only | Local evidence directory for `STORAGE_PROVIDER=local`. |

## Model provider

| Variable | Class | Production value / notes |
|---|---|---|
| `MODEL_PROVIDER` | Required | `groq` for this deployment. `ollama`/`openai-compatible` remain supported; `test` is refused in production. |
| `MODEL_BASE_URL` | Required | `https://api.groq.com/openai/v1` (preset). |
| `MODEL_NAME` | Required | `openai/gpt-oss-120b` (preset). |
| `GROQ_API_KEY` | Secret | Required when `MODEL_PROVIDER=groq`. Never logged or returned in errors. |
| `MODEL_REASONING_EFFORT` | Optional | `low` / `medium` / `high`; default `medium`. |
| `MODEL_TIMEOUT` | Optional | Seconds per model request, 1–60; default 30. One bounded retry, capped back-off for 429 and 5xx. |
| `MAX_STEPS` / `MAX_RUN_SECONDS` | Optional | Per-run agent step and time budgets; defaults 24 / 180. |

## First administrator (one-time)

| Variable | Class | Production value / notes |
|---|---|---|
| `BOOTSTRAP_ADMIN_EMAIL` | Optional (first deploy) | Real address of the first administrator. `@example.test` addresses are refused. |
| `BOOTSTRAP_ADMIN_PASSWORD` | Secret (first deploy only) | 12 or more characters. Used only while no user exists. Delete it from Render after the first successful start. |
| `BOOTSTRAP_ADMIN_NAME` / `BOOTSTRAP_WORKSPACE` | Optional | Display name and workspace name; defaults `Administrator` / `My workspace`. |

## Development only

| Variable | Notes |
|---|---|
| `SEED_PASSWORD` | Password for the sample `@example.test` accounts created by `python -m app.seed`. The seed refuses to run outside `development`/`test`. |
| `POSTGRES_USER` / `POSTGRES_DB` / `POSTGRES_PASSWORD` / `CONTAINER_MODEL_BASE_URL` | Local Compose settings only. |
| `TEST_DATABASE_URL`, `E2E_PASSWORD`, `QA_SCREENSHOT_DIR` | Automated tests and evaluation only. |
