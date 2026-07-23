# Deploying Leaf & Ledger

The app deploys as **one service**: the FastAPI backend serves both the API
(`/api/*`) and the built React frontend from the same address. There is no
separate frontend host to configure.

- **Database:** Supabase (Postgres), project `shnenpalzbcinkfltqcb`, region `us-east-1`
- **Logins:** Supabase Auth (ES256, verified against the project's public JWKS)
- **Host:** Render (or any host that can run a container and keep a process alive)

---

## Environment variables

### Backend (set these on the host)

| Variable | Required | What it is |
|---|---|---|
| `DATABASE_URL` | ✅ | Supabase Postgres connection string. Use the **transaction pooler** (port `6543`) for the running app. |
| `SUPABASE_URL` | ✅ | `https://shnenpalzbcinkfltqcb.supabase.co` — used to verify logins. |
| `ENV` | ✅ | Set to `supabase` in production so `.env.supabase` conventions apply. |
| `SUPABASE_JWT_SECRET` | ⬜ | Only needed if the project uses legacy HS256 signing. This project uses ES256, so **leave unset**. |
| `OPENAI_API_KEY` | ⬜ | Only for the AI Mockups page. Without it that one page returns a clear "not configured" error; everything else works. |
| `AUTH_DISABLED` | 🚫 | **Never set in production.** Local-dev escape hatch only, and it is ignored unless `ENV=dev`. |

### Frontend (set at **build** time)

Vite bakes these into the bundle when it builds, so they must be present on the
host as build environment variables — not just at runtime.

| Variable | Required | What it is |
|---|---|---|
| `VITE_SUPABASE_URL` | ✅ | `https://shnenpalzbcinkfltqcb.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | ✅ | The **anon / publishable** key from Settings → API. Public by design — safe in a browser. |

> ⚠️ Never set the Supabase **`service_role`** key anywhere in this app. It bypasses
> all database security. The app does not need it.

---

## Local development

Secrets live in git-ignored files (never commit them):

- `backend/.env.supabase` — `DATABASE_URL` + `SUPABASE_URL`
- `frontend/.env.local` — `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY`

Run the backend against Supabase:

```bash
cd backend && ENV=supabase .venv/bin/python -m uvicorn main:app --reload --port 8000
```

Run the frontend dev server (proxies `/api` to port 8000):

```bash
npm --prefix frontend run dev -- --port 5174
```

---

## Health check

`GET /health` is public and returns `{"status":"ok","auth":"required"}`. Point the
host's health check at it. It deliberately exposes nothing else.

---

## Database notes

- The running app uses the **transaction pooler** (`:6543`). asyncpg already passes
  `statement_cache_size=0`, which that pooler requires.
- **For dumps, restores, or any bulk load, use the DIRECT connection**
  (`db.<ref>.supabase.co:5432`). The pooler drops long `COPY` operations partway
  through with an SSL error, leaving a half-migrated database. This has bitten us
  once already.
- Supabase's **Data API is disabled** and Row Level Security is off. That is safe
  *only because* nothing is exposed over HTTP — the browser never queries Postgres
  directly; the FastAPI server does. **If the Data API is ever enabled, RLS must be
  enabled on every existing table first**, or the entire catalog becomes publicly
  readable.

---

## Security posture

- Every `/api/*` route requires a valid Supabase login. Tokens are verified
  cryptographically against the project's public keys — forged tokens are rejected.
- `backend/routers.json` is Databutton-generated scaffolding that marks every route
  `disableAuth: true`. **It is deliberately ignored.** Do not "fix" the code to
  honour it.
- Auth cannot be disabled in a deployed environment: the `AUTH_DISABLED` flag is
  only read when `ENV=dev`.
