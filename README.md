# IntelliStock

IntelliStock is an AI-based inventory management system that demonstrates operating-system concurrency control and database transaction safety alongside practical inventory tools. It combines process synchronization, the Banker's algorithm for warehouse resource allocation, priority scheduling, row-level locking with `SELECT ... FOR UPDATE`, AI-powered demand forecasting, and a live database chatbot into a single interactive dashboard.

## Phase 2 Feature Summary

The project now includes a complete operational dashboard and backend service layer with the following highlights:

- Architecture HUD: live system state banner showing concurrency, OS daemon activity, and AI forecasting status
- Viva Demo Bar: quick scenario runner for flash-sale race conditions, deadlock avoidance, and emergency stockout preemption
- Concurrency Waterfall: eight parallel API sales with measured latency and real HTTP status codes
- Banker's Lab: multi-resource allocation simulation for capacity, dock bays, and equipment
- Priority Queue Scheduler: non-preemptive priority queue with emergency stockout jumps to the front
- AI Demand Forecaster: 14-day demand prediction using regression-based forecasting logic
- Live Database Chatbot: natural-language inventory assistance for stock, capacity, and reorder questions
- Observability: authenticated app, database timing and optional Linux eBPF telemetry with a cross-platform fallback

## System Architecture

- `backend/`: FastAPI application, API routes, business logic, database sessions, and security configuration
- `frontend/`: React + Vite dashboard and interactive monitoring UI
- `ml_models/`: forecasting and AI reasoning modules
- `docker/`: containerization and local deployment support

## Core Technologies

- FastAPI for server-side APIs and business workflows
- PostgreSQL / SQLite for persistence and concurrency testing
- React + Vite for a responsive operational dashboard
- Tailwind-inspired styling and glassmorphism panels for visual clarity
- Framer Motion for smooth scenario playback and dashboard animation

## Setup and Execution

### Option A: SQLite demo (no Docker)

Requirements: Python, Node.js/npm, and PowerShell. Run the commands below from the repository root unless a step says otherwise. This option needs no Docker or PostgreSQL.

1. Create and activate a backend virtual environment, then install runtime dependencies:

   ```powershell
   python -m venv backend\.venv
   .\backend\.venv\Scripts\Activate.ps1
   python -m pip install -r backend\requirements.txt
   ```

2. Copy both example environment files. Generate unique local secrets and configure SQLite. The PowerShell snippet writes values directly to the untracked backend `.env`; it does not print them.

   ```powershell
   Copy-Item backend\.env.example backend\.env
   Copy-Item frontend\.env.example frontend\.env

   function New-RandomHex {
     $bytes = New-Object byte[] 32
     $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
     try {
       $rng.GetBytes($bytes)
       return [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
     } finally {
       $rng.Dispose()
     }
   }

   $values = @{
     SECRET_KEY = New-RandomHex
     INITIAL_ADMIN_PASSWORD = New-RandomHex
     OBSERVABILITY_INGEST_SECRET = New-RandomHex
     DATABASE_URL = 'sqlite:///./intellistock.db'
     ALLOW_SQLITE_FALLBACK = 'true'
   }
   $envPath = Join-Path (Get-Location) 'backend\.env'
   $content = Get-Content -LiteralPath $envPath -Raw
   foreach ($key in $values.Keys) {
     $pattern = '(?m)^' + [regex]::Escape($key) + '=.*$'
     $content = [regex]::Replace($content, $pattern, "$key=$($values[$key])")
   }
   [System.IO.File]::WriteAllText($envPath, $content, [System.Text.UTF8Encoding]::new($false))
   Remove-Variable values, content
   Remove-Item Function:\New-RandomHex
   ```

   The required settings are `SECRET_KEY`, `INITIAL_ADMIN_PASSWORD`, `OBSERVABILITY_INGEST_SECRET`, `DATABASE_URL=sqlite:///./intellistock.db`, and `ALLOW_SQLITE_FALLBACK=true`. Keep `CORS_ORIGINS` at `http://localhost:5173` and `VITE_API_BASE_URL` at `http://localhost:8000` for the default local setup. Do not commit either `.env` file. The admin password is read from `backend/.env` when the first admin is created; it is not replaced automatically on later starts.

   `APP_ENV` defaults to `development`. Example or missing ingest secrets produce a warning and disable ingest until a real secret is configured. Production requires non-placeholder secrets: `SECRET_KEY` (at least 32 characters), `INITIAL_ADMIN_PASSWORD` (at least 12 characters), and `OBSERVABILITY_INGEST_SECRET` (at least 32 characters). `ALLOW_PUBLIC_REGISTRATION` defaults to `false`; new users must be created by an authenticated ADMIN.

3. Seed the local database from the backend directory. This creates demo rows and the initial admin account:

   ```powershell
   Set-Location backend
   python -m scripts.seed_data
   ```

4. Start the backend in this terminal:

   ```powershell
   python -m uvicorn app.main:app --reload --port 8000
   ```

   The health endpoint is `http://localhost:8000/health`; it reports `active_database: sqlite`.

5. Open a second terminal at the repository root and install/start the frontend:

   ```powershell
   Set-Location frontend
   npm install
   npm run dev -- --host 0.0.0.0
   ```

6. Open `http://localhost:5173` and sign in with username `admin` and the `INITIAL_ADMIN_PASSWORD` stored in `backend/.env`.

The SQLite safe sale path uses an atomic conditional stock update, so concurrent safe sales preserve inventory correctly. SQLite does not support row-level `SELECT ... FOR UPDATE`; the row-locking comparison and the deliberately racy unsafe lost-update demonstration are meaningful only with PostgreSQL. Use Option B for that concurrency demo.

### Option B: PostgreSQL with Docker Compose

Requirements: Python, Node.js/npm, PowerShell, and Docker Desktop with Docker Compose.

1. Create/activate the backend virtual environment and install runtime dependencies as in Option A step 1. Copy `backend/.env.example` and `frontend/.env.example` to `.env` as in Option A step 2, then set the three required secrets there. Generate and write a matching PostgreSQL password without printing it:

   ```powershell
   $bytes = New-Object byte[] 32
   $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
   try {
     $rng.GetBytes($bytes)
     $dbPassword = [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
   } finally {
     $rng.Dispose()
   }
   $envPath = Join-Path (Get-Location) 'backend\.env'
   $content = Get-Content -LiteralPath $envPath -Raw
   $content = [regex]::Replace($content, '(?m)^POSTGRES_PASSWORD=.*$', "POSTGRES_PASSWORD=$dbPassword")
   $content = [regex]::Replace($content, '(?m)^DATABASE_URL=.*$', "DATABASE_URL=postgresql://postgres:$dbPassword@localhost:5432/intellistock")
   $content = [regex]::Replace($content, '(?m)^ALLOW_SQLITE_FALLBACK=.*$', 'ALLOW_SQLITE_FALLBACK=false')
   [System.IO.File]::WriteAllText($envPath, $content, [System.Text.UTF8Encoding]::new($false))
   Remove-Variable bytes, dbPassword, content
   ```

   Keep `CORS_ORIGINS=http://localhost:5173`. The same generated password is used for `POSTGRES_PASSWORD` and the URL; hex encoding makes it safe in the URL.

2. Start PostgreSQL from the repository root:

   ```powershell
   docker compose --env-file backend/.env -f docker/docker-compose.yml up -d db
   ```

3. Seed the database and start the backend in the activated environment:

   ```powershell
   Set-Location backend
   python -m scripts.seed_data
   python -m uvicorn app.main:app --reload --port 8000
   ```

4. In a second terminal, install and start the frontend as in Option A step 5. Sign in at `http://localhost:5173` with username `admin` and the `INITIAL_ADMIN_PASSWORD` in `backend/.env`.

For a VS Code dev tunnel, expose the frontend port. Set `VITE_API_BASE_URL=` (empty) and restart Vite to send browser requests through its same-origin `/api` proxy; this avoids requiring the browser to reach the workspace's `localhost:8000`. If you expose the API separately and set `VITE_API_BASE_URL` to that tunnel URL instead, `CORS_ORIGINS` must include the frontend origin (the `https://*.devtunnels.ms` pattern is allowed by default).

### Concurrency Demo Notes

Safe and unsafe modes send eight parallel requests to the real sale endpoints. On SQLite, safe mode uses an atomic conditional update and prevents overselling; SQLite ignores row-level `SELECT ... FOR UPDATE`, so the row-locking comparison and unsafe lost-update race are meaningful only on PostgreSQL. The UI displays each request's measured latency and HTTP status.

### Running tests

Run these commands from the repository root. The development requirements install the test runner and the TestClient transport dependency used by the current Starlette version.

```powershell
Set-Location backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
Set-Location ..\frontend
npx tsc -b
npm run build
```

The two database row-lock integration tests skip unless `TEST_DATABASE_URL` points to a dedicated PostgreSQL test database.

### Observability and chatbot

The backend uses application timing and best-effort process sampling by default. See [docs/EBPF_INTEGRATION.md](docs/EBPF_INTEGRATION.md) for the optional Linux/WSL2 collector, its limitations, and demo steps. Keep `OBSERVABILITY_INGEST_SECRET` private and configure the same value for the API and collector. The optional BCC sidecar is not required for Windows/macOS or normal API startup.

The Observability panel includes rolling latency and syscall charts, route request bars, and security-event breakdowns. The app-latency and route charts work with the SQLite/fallback demo; syscall, TCP and security-event charts need the optional eBPF collector. See [docs/METRICS_CHARTS.md](docs/METRICS_CHARTS.md) for data sources, interpretation, and a repeatable demo.

The chatbot classifier is an offline scikit-learn model. The training corpus is a small hand-curated set; its scores are indicative, not a guarantee of real-world intent recognition. On the fixed split, validation accuracy/macro-F1 were **0.898 / 0.900**. On 76 separate hand-written questions, accuracy/macro-F1 were **0.974 / 0.972**. A fresh 40-question blind set scored **0.975 / 0.975** once; one recommendation question was classified as out of scope. These small evaluation sets are not broad production benchmarks. See [the full evaluation and misses](docs/CHATBOT_EVALUATION.md). Rebuild the dataset with `python ml_models/chatbot/build_dataset.py`, then train with `python ml_models/chatbot/train.py` from the repository root. `model.joblib` is a pickle-based artifact: only load a copy produced from this trusted repository and training script, never an externally supplied model file.

## Project Workflow

The project is organized for phased development and validation. Each feature set is implemented, verified, and merged into the main branch once it passes the relevant build and runtime checks.

## Notes

The dashboard is intentionally designed to demonstrate both ideal safe behavior and risky unsafe states so the user can compare system behavior under concurrency pressure, deadlock risk, and scheduling stress in a controlled visual environment.

