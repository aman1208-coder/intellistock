# IntelliStock evaluator demo guide

## Pre-flight checklist

- Backend is running with seeded data and the admin user is present.
- `INITIAL_ADMIN_PASSWORD` is set before the backend starts so the default admin account can log in.
- Log in as `admin` from the app UI.
- Run the frontend with `npm run dev` from `frontend/`.
- Browser should be opened in full-screen for the live demo look.
- If you are testing through a VS Code dev tunnel, forward only the frontend port and set it to Public. The browser reaches the API through the Vite proxy, so the backend is not exposed directly.

## 5-minute flow

1. Open the login page and sign in as `admin`.
2. Click `Show scene` to hide the dashboard panels and reveal the solar system background.
3. Use the overview KPIs, donut chart, and warehouse capacity cards to walk through current inventory health.
4. Click `Demo 2` and then `Run Bankers check` to show the safety lab in action. A safe request is approved; an unsafe request is denied by the algorithm.
5. Click `Demo 3` and trigger the queue buttons to show priority jobs jumping the queue.
6. Open the forecast section and review the demand model.
7. Use the chatbot and ask: `Show me zero-stock items`.
8. Sign out to close the evaluation session.

## Feature truth table

| Feature | Status |
| --- | --- |
| Concurrency lab thread animation | SIMULATED (UI animation only) |
| Demo 1 race condition animation | SIMULATED (UI animation only) |
| Overview KPIs and donut chart | REAL (API-backed) |
| Warehouse capacity data | REAL (API-backed) |
| Banker's lab safety checks | REAL (API-backed) |
| Priority queue jobs | REAL (API-backed) |
| Demand forecast | REAL (API-backed) |
| Chatbot answer flow | REAL (API-backed) |
| Session sign-out flow | REAL (API-backed) |

## Likely mentor questions

- Why use row-level locking with `SELECT ... FOR UPDATE`? It prevents concurrent transactions from reading and writing the same inventory record at the same time, which eliminates lost-update races.
- What does the Banker's safe sequence guarantee? It ensures every resource request can finish without deadlock by checking the remaining resource graph before allocation.
- How are safety stock and reorder point computed? They are derived from demand history, service targets, and warehouse lead-time assumptions. The dashboard surfaces those decisions through current stock, threshold, and forecast values.
- What changes for deployment? The app should run behind a single secure API host or reverse proxy, with the backend and frontend behind a production web server, and all secrets loaded from environment variables instead of local dev tokens.
