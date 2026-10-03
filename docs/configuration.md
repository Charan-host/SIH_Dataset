# Local configuration and startup

The backend reads `DATABASE_URL` and `CORS_ORIGINS` from its process environment
and loads a project-root `.env` file when present. Copy `.env.example` as a
reference, provide real values through your local environment, a local `.env`
file, or a secret manager, and never commit a populated `.env` file.

From the project root, install and start the API with:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:DATABASE_URL = "postgresql://USERNAME:PASSWORD@HOST:PORT/DATABASE"
$env:CORS_ORIGINS = "http://localhost:5500,http://127.0.0.1:5500"
python -m uvicorn backend.main:app --reload --port 8000
```

Apply `database/schema.sql` and then `database/seed.sql` to a clean PostgreSQL
database with PostGIS installed. The seed file is demo-only and is not
idempotent; use a clean database for that sequence.

Serve `frontend/` with a static server on port 5500. In `frontend/config.js`,
set `apiBaseUrl` to the deployed API origin; leave it empty for local development,
which targets the current host on port 8000. Configure `CORS_ORIGINS` to include
the exact frontend origin(s).
