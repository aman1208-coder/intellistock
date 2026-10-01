# IntelliStock

IntelliStock is an AI-based inventory management system that demonstrates operating-system concurrency control and database transaction safety alongside practical inventory tools. It brings together process synchronization, the Banker's algorithm for warehouse resource allocation, priority scheduling, database row-level locking with `SELECT ... FOR UPDATE`, AI-powered demand forecasting, and a live database chatbot.

## Architecture

- `backend/`: FastAPI service, application configuration, API routes, and database integration.
- `frontend/`: Web client for inventory workflows and operational insights.
- `ml_models/`: Forecasting and AI components.
- `docker/`: Container and local deployment configuration.

The backend is organized into `core/` for configuration and security, `db/` for database setup and shared models, and `api/` for HTTP endpoints.

## Team Workflow

The project is developed by a two-person team using alternating ownership. Each phase is implemented on a focused feature branch, verified before it is shared, and merged into `main` so the next member can build on the latest integrated state. Keep commits scoped to the active phase and coordinate before merging concurrent work.

## Getting Started

Copy `backend/.env.example` to `backend/.env`, set the database connection and a private `SECRET_KEY`, then install the backend requirements and run the API from the `backend/` directory. To create the initial administrator, set a strong `INITIAL_ADMIN_PASSWORD` before the first startup; no default administrator password is enabled.

```bash
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API health check is available at `http://127.0.0.1:8000/health`.