# Leaf & Ledger — one image that serves both the app and the API.
#
# The frontend is built with Node, then handed to the Python image, which
# serves it alongside /api on a single origin. Two stages keep Node out of the
# final image.

# ---------- Stage 1: build the React app ----------
FROM node:20-slim AS frontend

WORKDIR /build

# Install dependencies first so this layer is cached unless the lockfile moves.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --legacy-peer-deps

COPY frontend/ ./

# Vite bakes these in at BUILD time, so they must be present here rather than
# only at runtime. Both are public values (see DEPLOYMENT.md).
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ENV VITE_SUPABASE_URL=${VITE_SUPABASE_URL}
ENV VITE_SUPABASE_ANON_KEY=${VITE_SUPABASE_ANON_KEY}

RUN npm run build

# Fail the build loudly if the app was built without a Supabase key — better
# than shipping a site where nobody can sign in.
RUN test -f dist/index.html \
    && if [ -z "$VITE_SUPABASE_ANON_KEY" ]; then \
         echo "ERROR: VITE_SUPABASE_ANON_KEY was empty at build time — sign-in would not work." >&2; \
         exit 1; \
       fi

# ---------- Stage 2: the Python service ----------
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libpq is needed by asyncpg's runtime; curl is used by the healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Install the backend's runtime dependencies. The `dev` group (tests, stubs)
# is deliberately left out of the image.
COPY backend/pyproject.toml ./backend/
RUN pip install --no-cache-dir uv \
    && cd backend \
    && uv pip install --system --group base --group app

COPY backend/ ./backend/

# The built app lands where main.py expects it: ../frontend/dist
COPY --from=frontend /build/dist ./frontend/dist

WORKDIR /app/backend

# Render (and most hosts) provide $PORT. Default to 8000 for a plain `docker run`.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
