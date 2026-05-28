# leaf-ledger

This is a full-stack application exported from Riff.

## Architecture

- **Frontend**: React + TypeScript + Vite
- **Backend**: Python + FastAPI
- **Database**: PostgreSQL (Neon)
- **Authentication**: Built-in auth system

## Quick Start

**See `GETTING_STARTED.md` for step-by-step setup instructions.**

This README provides technical reference and overview.

## Project Structure

```
.
├── backend/           # Python FastAPI backend
│   ├── app/          # Application code
│   │   ├── apis/     # API endpoints
│   │   ├── libs/     # Shared libraries
│   │   ├── auth/     # Authentication logic
│   │   └── ...
│   ├── .env          # Shared environment variables
│   ├── .env.dev      # Development environment variables
│   ├── .env.prod     # Production environment variables
│   └── pyproject.toml
├── frontend/          # React frontend
│   ├── src/
│   │   ├── pages/    # Page components
│   │   ├── components/ # Reusable components
│   │   └── ...
│   └── package.json
```

## Environment Variables

Backend environment variables are split across three files:

### `.env` (Shared)
- `DATABUTTON_PROJECT_ID`: Your project ID
- `DATABUTTON_CUSTOM_DOMAIN`: Custom domain configuration
- `DATABUTTON_EXTENSIONS`: Extension configuration

### `.env.dev` (Development)
- Development-specific secrets (database URLs, API keys, etc.)

### `.env.prod` (Production)
- Production-specific secrets (database URLs, API keys, etc.)

The backend automatically loads `.env` first, then overrides with `.env.dev` or `.env.prod` based on the `ENV` environment variable (defaults to `dev`).


### Database Connection Strings
Database connection strings are included in `.env.dev` and `.env.prod` for their respective environments.

## Development

### Install Dependencies

```bash
# Backend
cd backend
uv sync

# Frontend
cd frontend
yarn install
```

### Run Locally

```bash
# Terminal 1 - Backend
cd backend && ./run.sh

# Terminal 2 - Frontend
cd frontend && ./run.sh
```

## API Structure

API endpoints are defined in `backend/app/apis/`. The FastAPI app automatically registers routes based on the structure.

## Frontend Structure

React pages are defined in `frontend/src/pages/`. The app uses React Router for navigation.

## Limitations

This exported code doesn't include:
- Riff workspace features
- Platform-managed secrets (moved to .env)
- Automatic schedule execution (see SCHEDULES.md)
- Riff integrations

## Deployment

This app can be deployed to:
- Vercel (frontend) + Railway (backend)
- fly.io
- Google Cloud Run
- AWS
- Any hosting platform

## License

Your license here.
