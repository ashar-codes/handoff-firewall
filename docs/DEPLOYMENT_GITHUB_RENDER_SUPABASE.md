# Deploying Handoff Firewall: GitHub + Render + Supabase (hackathon/test)

This is a **test deployment** of the frozen alpha engine (`v0.1.0-alpha`), prepared on branch `deployment/hackathon`. It is not a production-readiness claim. The repository needs no editing. Every step below happens in your GitHub, Supabase or Render account.

## What gets deployed

```
Browser ──HTTPS──> Render web service (one container, one origin)
                     ├─ React UI          https://<service>.onrender.com/
                     ├─ FastAPI API        https://<service>.onrender.com/api/...
                     └─ durable worker     (same container)
                           ├─> Supabase PostgreSQL   (Session pooler, backend only)
                           ├─> Supabase Storage      (private bucket, backend only)
                           └─> Groq API              (backend only)
```

- The browser talks only to Handoff Firewall. It never receives database credentials, the Supabase secret key or the Groq key.
- Authentication is Handoff Firewall's own (secure cookies, CSRF, Origin checks, RBAC). Supabase Auth is not used.
- On every start the container validates configuration, then runs **upgrade-only** migrations under a PostgreSQL advisory lock, then optionally creates the first administrator, then starts one worker and the API. If either the worker or the API exits, the instance stops and Render restarts it.

Use only synthetic or explicitly approved data. Case documents and policy rules are sent to Groq for evidence extraction.

---

## 1. GitHub: private repository

1. In GitHub, create a **new private repository** (for example `handoff-firewall`). Do **not** add a README, `.gitignore` or licence; the repository already has them.
2. On your Mac, from the project folder, push the deployment branch and the alpha tag (replace the URL with your repository's):
   ```bash
   git remote add origin git@github.com:<you>/handoff-firewall.git
   git push -u origin deployment/hackathon
   git push origin alpha-quality-hardening v0.1.0-alpha   # optional: the frozen alpha for reference
   ```
3. Check in GitHub that no `.env` file appears anywhere in the repository. `.env` files are git-ignored, and the deployment preparation verified that none is tracked.

## 2. Supabase: database and private storage

1. **Create a project.** Choose a strong database password and save it in your password manager. Pick the region closest to the Render region you'll use.
2. **Close the Data API (mandatory).** Handoff Firewall never uses Supabase's browser-facing Data API, and leaving it open could let anyone holding the public "anon" key bypass Handoff Firewall's permissions.
   - Preferred: **Project Settings → Data API** → turn the Data API **off**. If your dashboard instead lists *Exposed schemas*, remove `public`.
   - Defence in depth (automatic): the first deploy runs migration `0004`, which revokes all `anon`/`authenticated` privileges on Handoff Firewall tables, sequences and functions. To confirm after the first deploy, run this in **SQL Editor**; it must return `0`:
     ```sql
     select count(*) from information_schema.role_table_grants
     where grantee in ('anon','authenticated') and table_schema = 'public';
     ```
3. **Database connection string.** Open **Connect** and choose **Session pooler** (IPv4, port `5432`). Copy the URI, which looks like:
   ```
   postgresql://postgres.<project-ref>:<db-password>@<pooler-host>:5432/postgres
   ```
   Append `?sslmode=require`. This is `DATABASE_URL`. Do not use the direct connection (IPv6-only without an add-on) or the transaction pooler (port 6543), because the worker relies on session-level row locking.
4. **Private storage bucket.** Go to **Storage → New bucket**:
   - name: `handoff-evidence`;
   - **Public bucket: off** (private);
   - optional file-size limit: 10 MB, the app's own limit.

   Do not add storage policies for `anon` or `authenticated`; only the backend reads and writes objects.
5. **Backend keys.**
   - **Project URL** (for example `https://<project-ref>.supabase.co`) is `SUPABASE_URL`.
   - **Project Settings → API Keys → Secret key** (`sb_secret_…`), or the legacy `service_role` key, is `SUPABASE_SERVICE_ROLE_KEY`. This key bypasses Row Level Security; put it only in Render. Never put it in the browser, chat or Git.
6. **Schema.** You don't need to create tables. The first Render start applies migrations `0001`–`0004` to the `public` schema. The sample-data seed is disabled in production.

## 3. Groq

In the Groq console, create an API key for the deployment and keep it for Render (`GROQ_API_KEY`). The free tier has daily token limits. When they're exhausted, model-dependent work falls back safely to manual review. That is visible in the case, never a false READY.

## 4. Render: one web service from the Blueprint

1. In Render, go to **New → Blueprint**, connect your GitHub account, and select the private repository.
2. Choose branch **`deployment/hackathon`**. Render reads `render.yaml`, which defines one **free** Docker web service named `handoff-firewall`. Rename it if you like. If Render's Blueprint validation rejects a field (for example the auto-deploy setting), adjust that field in the Render dashboard instead.
3. Render asks for the values marked `sync: false`. Enter:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | Supabase Session pooler URI with `?sslmode=require` |
   | `SUPABASE_URL` | `https://<project-ref>.supabase.co` |
   | `SUPABASE_SERVICE_ROLE_KEY` | Supabase secret key |
   | `GROQ_API_KEY` | Groq key |
   | `BOOTSTRAP_ADMIN_EMAIL` | your real email address |
   | `BOOTSTRAP_ADMIN_PASSWORD` | a new strong password, 12 or more characters (first deploy only) |
   | `FRONTEND_ORIGIN` | leave empty to use Render's service URL, or set `https://<your-service>.onrender.com` exactly (no trailing slash) |
   | `MIGRATION_DATABASE_URL` | leave empty |

   Everything else (`APP_ENV=production`, `COOKIE_SECURE=true`, `STORAGE_PROVIDER=supabase`, the Groq model, the bucket name, the small database pool) is preset by the Blueprint.
4. Deploy. The health check is `GET /api/health`, which also confirms the database is reachable. In the logs, expect:
   ```
   [start] validating configuration
   [start] app_env=production storage=supabase model=groq
   [start] applying database migrations (upgrade only)
   Database migrations are at head
   [start] first-administrator bootstrap check
   Administrator created; remove BOOTSTRAP_ADMIN_PASSWORD from the environment.
   [start] starting worker
   [start] starting API on port …
   ```
   If configuration is unsafe or incomplete (for example a missing key, an `http://` origin, or SQLite), the start fails immediately with a clear message.
5. After the administrator exists, **delete `BOOTSTRAP_ADMIN_PASSWORD`** in Render (Environment) and redeploy. Later starts print `Bootstrap skipped: a user already exists`, whatever the variables say. Bootstrap never creates sample accounts and refuses `@example.test` addresses.
6. Auto-deploy is off. Deploy new commits with **Manual Deploy** in Render.

## 5. Verify

1. Open `https://<your-service>.onrender.com`. The first request after inactivity can take a while (see Free-tier behaviour).
2. Sign in with the bootstrap email and password. Create further accounts in **Administration**.
3. Create a **New handoff** (workflows are created under **Workflows**; production starts empty), upload a small `.txt` evidence file, and click **Run investigation**. The case should move through the agents within seconds.
4. In Supabase **Storage → handoff-evidence**, confirm an object appeared under `<workspace>/<case>/<document>/v1/<file>`.
5. Run the SQL check from step 2.2; it must return `0`.
6. In Render **Logs**, worker lines (`app.worker`) and API lines (`uvicorn`) should appear, with no keys or passwords.

## Free-tier behaviour (Render and Supabase)

- **Render free web services sleep after inactivity.** The first request then waits for a cold start. **While the service sleeps the worker sleeps too**, so queued investigations resume only when the service wakes. No keep-alive pinging is configured; don't add one.
- **Ephemeral container disk.** Evidence lives in Supabase Storage; nothing needed survives on the container disk.
- **Supabase free projects can pause after inactivity.** While paused, health checks fail until you restore the project in the Supabase dashboard.
- **Scaling.** Scaling the Render service above one instance also adds workers. That's safe because job claims use PostgreSQL row locks, generation fencing and an advisory-locked migration, but stay at one instance for the hackathon.

## Backups and restore (not configured by this preparation)

No backups are configured by this preparation. Check your Supabase plan's backup coverage.

- **What to keep together:** the database (cases, facts, approvals, audit events, document metadata including SHA-256 hashes and object keys) and the Storage bucket (original evidence bytes). A restore needs **both from the same point in time**, or READY verification correctly fails on missing or changed originals.
- **Database:** take a logical dump through the Session pooler URI, for example `pg_dump --no-owner --format=custom "$DATABASE_URL" > handoff.dump`, while the service is paused or idle.
- **Storage:** download the `handoff-evidence` bucket, for example with the Supabase CLI or dashboard, keeping object keys unchanged.
- **Restore:** restore into a **new** Supabase project first, point a separate Render service at it, and confirm case counts, document hashes, approvals and that a waiting case resumes before relying on it. The repository's `scripts/backup.sh`/`restore.sh` cover the local Compose setup only.
