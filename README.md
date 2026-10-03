# CASC / OCEANTRACE

Oil spill investigation and vessel-attribution application with a plain HTML,
CSS, and JavaScript frontend, a FastAPI backend, and PostgreSQL/PostGIS storage.
The frontend uses Leaflet for the operational map.

## Repository layout

- `frontend/` — single-page interface and API-origin configuration.
- `backend/main.py` — FastAPI application and route registration.
- `backend/api/` — incident, detection, spill, drift, vessel, candidate, CASC,
  certificate, and audit endpoints.
- `backend/services/` — AIS, drift, candidate ranking, CASC, and persistence
  validation logic.
- `backend/database/` — SQLAlchemy connection setup and an optional database
  diagnostic command.
- `database/schema.sql` — PostgreSQL/PostGIS table definitions.
- `database/seed.sql` — demonstration records; the seed script is not
  idempotent.
- `tests/` — focused API route and transaction tests.
- `docs/` — local configuration and score/CASC semantics.

## Requirements

Python 3.10 or later, PostgreSQL with PostGIS, and the packages in
`requirements.txt`. PostgreSQL credentials belong in a local `.env` file or
environment variables; `.env` is ignored by Git. See
[`docs/configuration.md`](docs/configuration.md) for the local environment
configuration and CORS settings.

## Run locally

From the repository root in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --reload --port 8000
```

Serve the frontend separately on port 5500:

```powershell
python -m http.server 5500 --directory frontend
```

The frontend defaults to the API at the current host on port 8000. Set
`window.CASC_CONFIG.apiBaseUrl` in `frontend/config.js` when using a different
API origin. Add the exact frontend origin to `CORS_ORIGINS` in the backend
environment.

For a new database only, apply `database/schema.sql` and then
`database/seed.sql`. Do not run the seed script against an already seeded
database; it can insert duplicate records.

## API overview

The backend exposes `GET /health`, `GET /incidents/`, and incident-scoped GET
routes for detection, spill, drift, vessels, candidates, CASC, certificates,
and audit history. CASC execution is `POST /casc/{incident_id}/run`; the GET
route retrieves a persisted run. Certificate generation is
`POST /certificates/{incident_id}` and its GET route retrieves the persisted
certificate.

## CASC and data limitations

CASC evaluates variations in precomputed evidence scores (currently ±10%). It
does not perturb wind, current, AIS tracks, timestamps, spill geometry, or
source geometry. The current seeded incident has one distinct observed AIS
vessel; competitive stability against alternative observed vessels is
therefore not evaluated. Seeded fixture attribution scores are separate from
the runtime combined evidence score. Inputs and fixture records are identified
as demonstration data in the application. Additional details are in
[`docs/score-and-casc-semantics.md`](docs/score-and-casc-semantics.md).

## Tests and diagnostics

Run the automated tests from the repository root:

```powershell
python -m unittest discover -s tests -v
```

Run the optional PostgreSQL/PostGIS connectivity diagnostic with:

```powershell
python -m backend.database.diagnostics
```
