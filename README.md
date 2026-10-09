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

### Local Setup

Requirements: Python, Node.js/npm, and Docker Desktop with Docker Compose.

1. Configure local environment files. Do not commit either `.env` file or real credentials.

```powershell
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env
```

Edit `backend/.env`: set a unique `SECRET_KEY`, `INITIAL_ADMIN_PASSWORD` (before first startup), and matching PostgreSQL password in `DATABASE_URL` and `POSTGRES_PASSWORD`. Keep `CORS_ORIGINS` set to the frontend origin, normally `http://localhost:5173`. Edit `frontend/.env` to set `VITE_API_BASE_URL=http://localhost:8000`.

2. Start PostgreSQL from the project root:

```powershell
docker compose --env-file backend/.env -f docker/docker-compose.yml up -d db
```

3. Install backend requirements and seed the database. Run these commands from `backend/`; seeding creates missing reference/demo rows and creates the first admin when `INITIAL_ADMIN_PASSWORD` is configured.

```powershell
python -m pip install -r requirements.txt
python -m scripts.seed_data
python -m uvicorn app.main:app --reload --port 8000
```

The API health check is `http://localhost:8000/health`. Log in at `http://localhost:5173` with username `admin` and the `INITIAL_ADMIN_PASSWORD` configured before the first database initialization. An admin account is only created on first startup when that variable is set; an existing admin password is not replaced automatically.

4. In another terminal, install and start the frontend:

```powershell
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

For a VS Code dev tunnel, expose the frontend port. Set `VITE_API_BASE_URL=` (empty) and restart Vite to send browser requests through its same-origin `/api` proxy; this avoids requiring the browser to reach the workspace's `localhost:8000`. If you expose the API separately and set `VITE_API_BASE_URL` to that tunnel URL instead, `CORS_ORIGINS` must include the frontend origin (the `https://*.devtunnels.ms` pattern is allowed by default).

### Concurrency Demo Notes

Safe and unsafe modes send eight parallel requests to the real sale endpoints. SQLite ignores row-level `SELECT ... FOR UPDATE`, so the locking comparison (including the unsafe lost-update race) is meaningful only on PostgreSQL. The UI displays each request's measured latency and HTTP status.

Run tests from the project root:

```powershell
cd backend
python -m pytest -q
cd ../frontend
npx tsc -b
npm run build
```

The two database row-lock integration tests skip unless `TEST_DATABASE_URL` points to a dedicated PostgreSQL test database.

## Project Workflow

The project is organized for phased development and validation. Each feature set is implemented, verified, and merged into the main branch once it passes the relevant build and runtime checks.

## Notes

The dashboard is intentionally designed to demonstrate both ideal safe behavior and risky unsafe states so the user can compare system behavior under concurrency pressure, deadlock risk, and scheduling stress in a controlled visual environment.

