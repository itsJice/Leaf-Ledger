# Getting Started with leaf-ledger

Follow these steps to get your exported app running locally.

## Prerequisites

- [ ] Python 3.11 installed
- [ ] Node.js 18+ installed
- [ ] `uv` package manager installed (`pip install uv`)
- [ ] `yarn` package manager enabled (`corepack enable`)

## Step 1: Database Setup

Your database connection strings are configured in `backend/.env.dev` (development) and `backend/.env.prod` (production).

- [ ] **Option A:** If you transferred database ownership, it's already set up ✅
- [ ] **Option B:** If you haven't transferred the database yet:
  - Visit your Riff app settings
  - Click "Transfer Database Ownership"
  - Follow the claim link to claim your database
  - Connection strings in `.env.dev` and `.env.prod` will continue to work

## Step 2: Install Dependencies

- [ ] Install backend dependencies:
  ```bash
  cd backend
  uv sync
  ```

- [ ] Install frontend dependencies:
  ```bash
  cd frontend
  yarn install
  ```

## Step 3: Set Up Schedules (if applicable)

See `SCHEDULES.md` for a list of scheduled jobs that were configured in Riff.

- [ ] Choose a scheduler (cron, systemd timers, GitHub Actions, etc.)
- [ ] For each schedule in SCHEDULES.md, create a cron job or scheduled task that calls the endpoint
- [ ] Example cron entry:
  ```bash
  0 9 * * * curl -X POST http://localhost:8000/api/send-daily-report
  ```

## Step 4: Run the App

- [ ] Start backend (in one terminal):
  ```bash
  cd backend
  ./run.sh
  ```

- [ ] Start frontend (in another terminal):
  ```bash
  cd frontend
  ./run.sh
  ```

- [ ] Visit http://localhost:5173

## Step 5: Verify Everything Works

- [ ] App loads in browser
- [ ] You can log in (if using authentication)
- [ ] Database queries work
- [ ] API endpoints respond correctly

## What Doesn't Work?

These Riff platform features are not available in the exported code:

- ❌ Riff secrets management (use .env files instead)
- ❌ Riff integrations
- ❌ Automatic schedule execution (set up manually with cron)
- ❌ Riff workspace features (preview, logs, database explorer)

## Need Help?

- **Database issues?** Make sure you claimed ownership in Riff
- **Schedules?** See SCHEDULES.md for all configured jobs
- **Technical details?** See README.md for architecture overview

## Next Steps

- [ ] Set up schedules in your production environment
- [ ] Deploy to your hosting platform (Vercel, Railway, fly.io, etc.)
- [ ] Set up CI/CD if needed
- [ ] Configure production environment variables
