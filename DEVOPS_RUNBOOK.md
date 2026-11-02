# IntelliStock Deployment Runbook

## Requirements

- Docker Desktop or Docker Engine with Docker Compose v2
- A unique database password and JWT signing key

## Configure

From the repository root, create the local environment file:

```powershell
Copy-Item backend/.env.example backend/.env
```

Set `POSTGRES_PASSWORD`, `SECRET_KEY`, and `INITIAL_ADMIN_PASSWORD` in `backend/.env`. Use URL-safe characters for `POSTGRES_PASSWORD`, because Compose inserts it into the SQLAlchemy connection URL. Set `CORS_ORIGINS` to the public frontend origin if the browser will call the API directly. The default container frontend uses an Nginx same-origin `/api` proxy.

Do not commit `backend/.env`. For a managed production deployment, inject credentials through the platform's secret manager instead of storing them in a Compose environment file, and terminate TLS at a trusted ingress or reverse proxy.

## Build And Start

Run the full stack from the repository root:

```powershell
docker compose --env-file backend/.env -f docker/docker-compose.yml up --build -d
```

Compose builds the FastAPI image and static frontend image, starts PostgreSQL with a persistent named volume, waits for database/API health checks, and then starts the frontend.

Check service health and startup logs:

```powershell
docker compose --env-file backend/.env -f docker/docker-compose.yml ps
docker compose --env-file backend/.env -f docker/docker-compose.yml logs -f backend frontend
```

Seed demo warehouses, products, customers, and transaction history once the services are healthy:

```powershell
docker compose --env-file backend/.env -f docker/docker-compose.yml exec backend python -m scripts.seed_data
```

The seed operation is idempotent and fills the transaction history to its configured target. The admin account is created on first database initialization when `INITIAL_ADMIN_PASSWORD` is set; changing that environment variable does not reset an existing password.

## Verify

- Dashboard: `http://localhost:8080` (or the configured `FRONTEND_PORT`)
- API health: `http://localhost:8000/health` (or the configured `API_PORT`)
- Swagger UI: `http://localhost:8000/docs`
- Sign in with username `admin` and the configured initial admin password.

To run the project tests and frontend production build on the host:

```powershell
python -m unittest discover -s backend/tests -v
npm --prefix frontend run build
```

The PostgreSQL row-lock behavior can only be demonstrated against PostgreSQL; SQLite does not implement `SELECT ... FOR UPDATE` row locking.

## Stop And Data Retention

Stop containers without deleting database state:

```powershell
docker compose --env-file backend/.env -f docker/docker-compose.yml down
```

The `intellistock-postgres` volume persists across restarts. Removing volumes with `docker compose down -v` permanently deletes the database and should be reserved for an intentional reset after taking any required backups.