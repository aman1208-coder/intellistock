# IntelliStock

IntelliStock is an AI-based inventory management system that demonstrates operating-system concurrency control and database transaction safety alongside practical inventory tools. It combines process synchronization, the Banker's algorithm for warehouse resource allocation, priority scheduling, row-level locking with `SELECT ... FOR UPDATE`, AI-powered demand forecasting, and a live database chatbot into a single interactive dashboard.

## Phase 2 Feature Summary

The project now includes a complete operational dashboard and backend service layer with the following highlights:

- Architecture HUD: live system state banner showing concurrency, OS daemon activity, and AI forecasting status
- Viva Demo Bar: quick scenario runner for flash-sale race conditions, deadlock avoidance, and emergency stockout preemption
- Concurrency Waterfall: thread-based visualization of safe vs. unsafe locking behavior
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

### Backend

From the project root, install the backend dependencies and start the API:

```bash
cd backend
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The API health check is available at `http://127.0.0.1:8000/health`.

### Frontend

From the project root, install the frontend dependencies and run the dashboard:

```bash
cd frontend
npm install
npm run dev
```

The React application will be served through the Vite development server for local interaction.

## Project Workflow

The project is organized for phased development and validation. Each feature set is implemented, verified, and merged into the main branch once it passes the relevant build and runtime checks.

## Notes

The dashboard is intentionally designed to demonstrate both ideal safe behavior and risky unsafe states so the user can compare system behavior under concurrency pressure, deadlock risk, and scheduling stress in a controlled visual environment.

