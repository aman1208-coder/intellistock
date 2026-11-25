# Two-port demo roles

The demo accounts are provisioned by `python -m scripts.create_demo_users` from
`backend/`. Their randomly generated passwords are stored only in the ignored
`backend/demo_credentials.local.txt` file.

From the repository root, run `.\start_demo.ps1`. Forward ports 8000, 5173,
and 5174 in VS Code; use 5173 for ADMIN and 5174 for STAFF. Stop only the demo
processes launched by that script with `.\stop_demo.ps1`.

There is no public registration. An authenticated ADMIN creates STAFF member
accounts from the Members panel; admins can activate or deactivate accounts
and issue a one-time temporary password reset. `ALLOW_PUBLIC_REGISTRATION`
defaults to `false` and never bypasses the administrator requirement.

| Feature | ADMIN | STAFF (`demo_member`) |
| --- | --- | --- |
| Products | View products and recommendations; add, adjust, and delete products (subject to inventory/history constraints). | View products and recommendations. Product changes are not available. |
| Safe/unsafe waterfall | Run eight concurrent safe or unsafe sale requests. | Not available; both transaction endpoints require ADMIN or WAREHOUSE_MANAGER. |
| Banker's lab | Reset warehouse allocation state and run safe/unsafe allocation checks. | Not available; the demo reset endpoint is ADMIN-only. |
| Priority queue | View jobs and enqueue urgent stock checks or routine audits. | View jobs only; enqueuing requires a manager role. |
| Forecast | View product demand forecasts and run reorder analysis. | View product demand forecasts; reorder analysis is not available. |
| Chatbot | Ask inventory questions, including “any suspicious activity”. | Same authenticated chatbot access as ADMIN. |
| Observability | View authenticated metrics/charts and run the load generator. | View authenticated metrics/charts; load generation is replaced by a role explanation because it submits protected inventory transactions. |
| Live transactions | View/filter transaction history and create product transactions through product management controls. | View/filter transaction history. |

These are API-backed permissions: product, transaction-write, reorder-analysis,
priority-queue-write, allocation, and sale endpoints enforce roles in the
backend. Read endpoints require authentication. The frontend hides or explains
controls that STAFF cannot use instead of relying on a failed 403 response.

The safe/unsafe comparison is a true database locking demonstration only with
PostgreSQL; SQLite does not implement `SELECT ... FOR UPDATE`.
