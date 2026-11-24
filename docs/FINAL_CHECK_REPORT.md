# IntelliStock final security and release check

Audit date: 2026-11-24. This report records observed code and command results from the current working tree. It is not a clean release sign-off: the repository has uncommitted changes, Docker Desktop's Linux engine was unavailable, and some requested end-to-end scenarios could not be run.

## Summary

- `python -m pytest -q` from `backend/`: **31 passed, 2 skipped**. The skips are PostgreSQL row-lock integration tests, which require `TEST_DATABASE_URL`.
- `npx tsc -b` and `npm run build` from `frontend/`: **passed**; Vite produced the frontend bundle.
- The original audit's perfect training-distribution score came from generated, duplicated examples and was misleading. It is superseded by the Phase 3 evaluation: validation **0.898 accuracy / 0.900 macro-F1**, 76-question held-out **0.974 / 0.972**, and once-run 40-question blind **0.975 / 0.975**. These small sets are indicative only; see [CHATBOT_EVALUATION.md](CHATBOT_EVALUATION.md).
- Fresh-tree SQLite seed and API smoke test passed for the endpoints/scenarios listed below. It was a temporary copy of the available tree, not a Docker/Postgres clone test.
- WSL2 BPF programs compiled and attached on kernel `6.6.114.1-microsoft-standard-WSL2`; the collector could not publish because the API was not running. End-to-end eBPF ingest/UI and Compose sidecar were not verified.
- No real credential was identified in the scanned tracked files/history. Placeholder values in `.env.example` are intentionally public; using them as actual deployment values is unsafe.
- Fixes made during this audit are uncommitted. `git status --short` is not clean; it includes these edits and existing/generated changes. No commit was made.

## Findings

| Severity | File and line | Verified issue and impact | Fix / disposition |
|---|---|---|---|
| High | [backend/app/api/auth.py](../backend/app/api/auth.py#L14) | `POST /api/auth/register` has no authentication dependency and creates an active STAFF account. The new account can access protected inventory and transaction reads. This is a public account-creation/data-access surface. | Needs your decision before changing API behavior: disable public registration, require an invitation, or keep it intentionally public. |
| High | [backend/.env.example](../backend/.env.example#L2), [backend/.env.example](../backend/.env.example#L7), [backend/app/core/config.py](../backend/app/core/config.py#L14) | The copied example contains publicly known values for `SECRET_KEY` and `INITIAL_ADMIN_PASSWORD`. README instructs operators to replace them, but if that step is missed JWTs can be forged and the initial `admin` password is predictable. Compose requires a nonempty key, but accepts the example placeholder. | Needs approval for startup validation that rejects known placeholders and requires strong secrets outside development. Rotate any deployed values if these placeholders were used. No real secret was found committed in this scan. |
| Medium | [backend/app/core/config.py](../backend/app/core/config.py#L14) | If `SECRET_KEY` is omitted, `secrets.token_urlsafe(32)` is generated on each process start. Restarting invalidates issued JWTs; multiple workers can also disagree on token validity. | Persist a strong environment secret; fail fast outside local development. This overlaps the placeholder enforcement decision above. |
| Medium | [backend/app/main.py](../backend/app/main.py#L31) | CORS allows credentialed requests from every matching `https://*.devtunnels.ms` origin and allows all methods/headers. This is useful for demos but broader than a production origin allowlist. | Use exact configured origins for production and gate tunnel regex to development. |
| Medium | [backend/app/api/auth.py](../backend/app/api/auth.py#L37) | Login has no rate limiting or lockout, so password guessing is not throttled at the application layer. No login abuse control was found in the inspected route/middleware. | Add a deployment-level or application rate limit before exposing login publicly; document current limitation. |
| Medium | [backend/app/services/priority_scheduler.py](../backend/app/services/priority_scheduler.py#L41), [backend/app/api/concurrency.py](../backend/app/api/concurrency.py#L211) | `PriorityQueue` is unbounded and manager users can enqueue repeatedly. Authentication reduces exposure but does not cap memory growth. | Add queue capacity/retention or request throttling after deciding the desired demo behavior. |
| Medium | [backend/app/db/session.py](../backend/app/db/session.py#L34) | A PostgreSQL connection failure during engine initialization silently switches the process to `./intellistock.db` SQLite. Subsequent writes can go to a separate database without the operator realizing Postgres is unavailable; SQLite also cannot demonstrate row locks. | Needs behavior approval: make fallback explicit/configurable and log/report it prominently, or fail startup when Postgres was selected. |
| Medium | [backend/app/services/chatbot.py](../backend/app/services/chatbot.py#L262), [backend/app/services/chatbot.py](../backend/app/services/chatbot.py#L271) | API latency is formatted as measured p50/p95 even with zero samples (the store returns percentile `0.0`). The system-health branch can also see fallback CPU values while no request/DB data exists. This can present missing telemetry as measured zero or infer a bottleneck from absent data. | Needs approval because it changes user-visible answer behavior. Return explicit unavailable state until relevant samples exist. |
| Medium | [frontend/package.json](../frontend/package.json), [frontend/package-lock.json](../frontend/package-lock.json) | `npm audit` reported a High Vite advisory and Moderate esbuild advisory; the reported remediation requires Vite 8, a major upgrade from Vite 5.4.21. | Ask before the major toolchain upgrade. No frontend dependency upgrade was applied. Re-run `npm audit` after the decision. |
| Medium | [backend/requirements.txt](../backend/requirements.txt) | `pip-audit -r requirements.txt` reported `python-jose 3.5.0` (`PYSEC-2026-4298`) and `ecdsa 0.19.2` (`PYSEC-2026-1325`, dependency path). The audit output did not identify a fix version. | Investigate fixed versions and compatibility, then upgrade safely and rerun tests. No major dependency change was made. |
| Medium | [ml_models/chatbot/data/intents.jsonl](../ml_models/chatbot/data/intents.jsonl), [ml_models/chatbot/train.py](../ml_models/chatbot/train.py) | Original 600-row generated corpus had duplicate and cross-split text leakage, making its perfect split score unsuitable as a real-world estimate. | **Fixed for Phase 3:** replaced with 980 authored examples, 60+ per intent; the builder removes exact/near duplicates and checks separation from the hand-written set. Tests check separation from both evaluation sets. Held-out and blind scores are recorded in [CHATBOT_EVALUATION.md](CHATBOT_EVALUATION.md). The sets are small, so scores remain indicative. |
| Low | [docker/docker-compose.ebpf.yml](../docker/docker-compose.ebpf.yml#L2) | Optional `ebpf` profile uses `privileged: true`, host PID, writable `/sys/kernel/debug` and `/sys/fs/bpf`, and kernel mounts. It is a broad host-level grant. The file is labeled development-only in docs, but the Compose profile itself is not an enforced safety boundary. | Keep disabled by default; for production replace with a dedicated node agent and narrowly scoped capabilities. Do not run this override on shared/production hosts. |
| Low | [backend/Dockerfile](../backend/Dockerfile#L1), [frontend/Dockerfile](../frontend/Dockerfile#L1) | Application runtime users are non-root (`USER app` for backend and `nginx-unprivileged` frontend), and healthchecks exist in Compose. Base images use moving tags (`python:3.12-slim`, `node:22-alpine`, `postgres:16-alpine`), not immutable digests. | Pin image digests for reproducible release builds. PostgreSQL has no host port mapping in the inspected Compose file. |
| Low | [README.md](../README.md) | A tracked MIT [LICENSE](../LICENSE) exists with copyright attribution `its_mj`, but the README does not link to the license or identify the author/maintainer. | Add a README license link and author/maintainer credit if desired; the repo already has a license file, so do not create a duplicate or invent an identity. |

## Route/authentication inventory

Inspected routers under `backend/app/api/`:

| Route(s) | Authorization observed |
|---|---|
| `POST /api/auth/login` | Public, as expected. |
| `POST /api/auth/register` | Public; creates STAFF account (High finding above). |
| `/api/ai/chatbot`, `/api/chatbot/query`, recommendation aliases, `/api/ai/forecast/{product_id}` | Valid active-user bearer token. |
| `POST /api/ai/run-reorder-analysis` | `ADMIN` or `WAREHOUSE_MANAGER`. |
| Products and warehouses list/get | Valid active-user bearer token. |
| Product create/update/delete; warehouse create/update; transaction create | `ADMIN` or `WAREHOUSE_MANAGER`. |
| Transaction list | Valid active-user bearer token. |
| Concurrency allocation, queue-job, safe/unsafe sale | `ADMIN` or `WAREHOUSE_MANAGER`. |
| Priority queue read | Valid active-user bearer token. |
| Warehouse-state reset | `ADMIN`. |
| Observability status, metrics, DB latency, network, security-events | Valid active-user bearer token. |
| `POST /api/observability/ingest` | Shared-secret authentication; it rejects absent/unconfigured/placeholder or under-32-character configured secrets with 503, rejects absent/wrong header with 401, and uses `secrets.compare_digest`. |
| `GET /health`; FastAPI docs/OpenAPI defaults | Public. |

`core/security.py` inspection confirmed bcrypt hashing, JWT expiry, and decode algorithm allowlist equal to configured `settings.algorithm`; no `none` algorithm is included by the decoder. Search found no password/token logging. Configurable `ALGORITHM` is an operator setting. ORM query construction in the inspected API/service paths uses SQLAlchemy expressions; product/transaction/warehouse pagination limits are capped at 100 and observability event limit at 500. The chatbot question limit is 500 characters. No `dangerouslySetInnerHTML` use was found; React text interpolation is used for chatbot answers and event details. This is a code inspection, not a penetration test.

## Secrets, input bounds, and network notes

- `git ls-files` showed `.env.example` files but no tracked non-example `.env`, `*.db`, or SQLite files. `git grep` and history patch searches did not identify real API tokens or credentials; matches were placeholders/config variable names. No history rewrite was performed. Model artifact `model.joblib` is tracked but is not a credential.
- `.gitignore` and `.dockerignore` cover environment files (while allowing `.env.example`), DB/SQLite files, Python caches, node_modules, IDE and dev-tunnel folders. Model artifacts are deliberately included in the app image and repository; they are required for the chatbot. The joblib load path is fixed in code and the artifact is generated by `train.py`, not downloaded. Since joblib/pickle can execute code, only trust the repository-produced artifact; that warning was added to README/source.
- Ingest schema now applies numeric bounds and limits event list to 100, strings, maps, probe list, and map cardinalities. Store ring buffers cap requests, DB samples, and events at 1,000; per-route metrics are cardinality bounded. No ingress rate limiting was verified. A client with the ingest secret can still send repeated accepted payloads; request rate limiting is recommended.
- Collector BPF load exceptions are caught and return a nonzero exit rather than crashing with an uncaught traceback. Active collector filters event paths in user space and publishes generic details rather than path contents. The standalone `ebpf/probes/security.c` example emits a filename to its perf buffer; it is an example probe, not the active collector implementation. Treat it as sensitive telemetry if activated.
- Docker backend runtime is non-root and has a healthcheck. Compose exposes API/frontend ports for local access, but not Postgres. Docker image tags are not digest-pinned. Normal API Compose config does not grant kernel privileges; the optional collector profile is privileged.
- Basic security response headers (`nosniff`, frame deny, strict-origin referrer policy) were added. No app-level login or ingest rate limiter was added.

## Changes made during this audit

- Tightened observability ingest field bounds and secret validation; added tests for missing/placeholder secrets and payload limits.
- Bounded per-route metric cardinality and returned to fallback after stale eBPF reports; preserved local DB timing when the sidecar sends no DB samples.
- Added basic response headers and route-template aggregation to avoid attacker-controlled path cardinality.
- Added username/password bounds including bcrypt UTF-8 byte length validation.
- Expanded `.gitignore`/`.dockerignore` for IDE, tunnel, and SQLite side files; changed the sample PostgreSQL password to an explicit placeholder.
- Documented joblib trust requirements, corrected eBPF documentation to reflect the actual WSL2 probe-load check, and added README instructions for the tested SQLite fallback.
- Added observability tests. No DB schema migration, route addition, chatbot rewrite, major dependency upgrade, or commit was made. Ingest validation and the accepted input bounds were tightened; that changes which ingest payloads are accepted and should be reviewed before retaining, consistent with the requested approval rule for API contract changes.

## Commands and results

| Check | Result |
|---|---|
| `cd backend; python -m pytest -q` | **31 passed, 2 skipped**, one Starlette/httpx deprecation warning. Skipped tests require a dedicated `TEST_DATABASE_URL` PostgreSQL instance for row-lock behavior. |
| `cd frontend; npx tsc -b` | Passed. |
| `cd frontend; npm run build` | Passed; Vite 5.4.21 built 448 modules. |
| `python ml_models/chatbot/train.py` (Phase 3 final run) | Exited successfully; validation accuracy 0.8980 and macro-F1 0.8998; held-out accuracy 0.9737 and macro-F1 0.9722; blind accuracy 0.9750 and macro-F1 0.9751 (blind inference run once after model freeze). See [CHATBOT_EVALUATION.md](CHATBOT_EVALUATION.md). |
| Fresh-tree `python -m scripts.seed_data` | Passed in a temporary copy using SQLite fallback; generated demo rows and an admin using an audit-only dummy password. |
| Fresh-tree API smoke with FastAPI `TestClient` | Passed: admin login, products and warehouses (200); eight parallel safe and eight parallel unsafe sale requests (all 201); Banker allocation (200); priority queue read/enqueue (200/201); forecast (200); 12 chatbot prompts all 200 including out-of-scope and gibberish; observability status/metrics (200, fallback mode). This does not prove PostgreSQL locking behavior or browser rendering. |
| `docker compose version` / `docker info` | Compose v5.1.3 available; Docker Engine unavailable (Docker Desktop Linux engine pipe missing). Therefore PostgreSQL startup and full README Docker/Postgres fresh-clone path were **not run**. |
| `pip-audit -r backend/requirements.txt` | Reported `python-jose 3.5.0 PYSEC-2026-4298` and `ecdsa 0.19.2 PYSEC-2026-1325`; no dependency change made. |
| `npm audit --json` in frontend | High Vite and Moderate esbuild findings; remediation offered by audit is major Vite 8 upgrade. No major upgrade made. |
| `pip list --outdated` | Run against the global Python 3.14 environment, not an isolated project virtualenv; output is not a reliable project-specific outdated-dependency inventory. `pip-audit -r` is the requirements-level audit result above. |
| WSL2 eBPF load | WSL2 Ubuntu kernel `6.6.114.1-microsoft-standard-WSL2`; collector printed that probes loaded for PID 1, then ingest publish failed with connection refused because no API was running. Probe load was verified; ingest/UI were not. |

Fresh-tree limitation: the README's Postgres step could not proceed because Docker Engine was unavailable. The temporary SQLite test established that seed and API startup paths worked in that local environment; it did not establish an offline install from a cold dependency cache or the exact README Postgres startup sequence. Network-isolated operation was not explicitly tested.

## Honest feature matrix

| Feature | Status | Evidence / limit |
|---|---|---|
| Login and protected dashboard API reads | Working and tested | TestClient login, product and warehouse reads; API route dependencies inspected. Public self-registration remains a security decision. |
| Product and transaction workflow | Working and tested | Products read and sale requests returned success in temporary SQLite smoke. Full browser flows and Postgres transaction semantics not tested. |
| Safe/unsafe concurrency comparison | Example only | Both endpoints returned success in SQLite; SQLite ignores `SELECT FOR UPDATE`, so the waterfall does not verify PostgreSQL row-lock race behavior. PostgreSQL integration tests skipped. |
| Banker's resource allocation | Working and tested | One allocation request passed through the API smoke; not a broad correctness proof. |
| Priority scheduler | Example only | Read and enqueue API smoke passed; this is an in-memory, unbounded demo queue, not a durable worker system. |
| Demand forecast | Working and tested | Forecast endpoint returned 200 for a seeded product; predictive quality was not independently evaluated. |
| Chatbot database/observability answers | Working and tested | Earlier 15/30 routing result is superseded by Phase 3 evaluation: 76 held-out questions scored 0.974 accuracy/0.972 macro-F1; a fresh 40-question blind run scored 0.975/0.975. These are small indicative intent-routing results, not a correctness guarantee for database facts. |
| Fallback observability | Working and tested | Fresh-tree API smoke returned fallback status/metrics. Not all host/database metrics exist in fallback mode. |
| eBPF probe compilation/attachment | Working and tested (WSL2 probe load only) | BCC probes loaded on the reported WSL2 kernel. End-to-end ingest/dashboard is not verified. |
| eBPF ingest and dashboard | Not verified | Collector could not reach an API during probe test; Compose sidecar not run. |
| PostgreSQL row-lock behavior | Not verified | Docker Engine unavailable and PostgreSQL tests skipped. |
| Optional external LLM | Not implemented | Flags/API key settings exist but inspected chatbot path does not call an external model; `CHATBOT_LLM_ENABLED` defaults false. |
| TCP resets, connection failures/rate, RTT, child ancestry | Not implemented | Documented collector limitations; current active probes only count host-wide retransmits for TCP. |

No claims are made here about browser-based XSS testing, PostgreSQL locking, end-to-end eBPF, or offline cold installation; those were not exercised.

## Checks not verified and exact WSL2/Linux commands

1. **PostgreSQL-backed tests and concurrency:** start the configured database, create a dedicated test database, then from `backend/` set `TEST_DATABASE_URL='postgresql+psycopg2://USER:PASSWORD@HOST:5432/intellistock_test'` and run `python -m pytest -q`. Do not point tests at production data. Inspect safe/unsafe waterfall under PostgreSQL after seeding; SQLite is not equivalent.
2. **eBPF end-to-end:** from repo root, run `uname -r`, `sudo bpftool feature probe kernel`, and `sudo cat /sys/kernel/tracing/available_events | grep -E 'raw_syscalls:sys_(enter|exit)|sched:sched_(switch|wakeup|process_exec)|tcp:tcp_retransmit_skb|syscalls:sys_enter_openat'`. Start API with a non-placeholder shared secret, run `pgrep -af 'uvicorn app.main:app'`, then `sudo env BACKEND_PID=<actual-worker-pid> OBSERVABILITY_INGEST_SECRET='<same-32+-char-secret>' OBSERVABILITY_INGEST_URL='http://127.0.0.1:8000/api/observability/ingest' SENSITIVE_PATHS='/.env,/etc/passwd,/etc/shadow,/.ssh,intellistock.db' python3 ebpf/collector.py`. Confirm authenticated `/api/observability/status` says `collector: ebpf`, then check `/api/observability/metrics`. Do not use a host secret as a test file.
3. **Compose eBPF profile:** only on an isolated Linux demo host, inspect `docker compose --env-file backend/.env -f docker/docker-compose.yml -f docker/docker-compose.ebpf.yml --profile ebpf config`, then follow [ebpf/README.md](../ebpf/README.md). This profile is privileged and host-PID; do not run it on a shared/production host.
4. **Cold/offline install:** not verified. With network disabled and a clean Python/npm cache, recreate the temp copy and follow README install steps. A cached build is not evidence of offline dependency installation.
5. **Browser UI and visual XSS:** not verified with a browser automation session. Test rendered user-provided strings in chatbot/security-event views in a browser after starting the app.

## Demo checklist (10 steps)

1. **Choose runtime:** preferred demo is Docker Compose/PostgreSQL on a machine with Docker Engine. If Docker is unavailable, use local backend SQLite fallback and be explicit that row-lock behavior is not demonstrated.
2. **Set environment:** copy `backend/.env.example` to `backend/.env`; set unique random `SECRET_KEY`, strong `INITIAL_ADMIN_PASSWORD`, and matching Postgres password. Never use example placeholder values.
3. **Start database:** from repo root run `docker compose --env-file backend/.env -f docker/docker-compose.yml up -d db`; wait for healthy status. If unavailable, switch to SQLite fallback and state the limitation.
4. **Seed backend:** from `backend/`, install `python -m pip install -r requirements.txt`; run `python -m scripts.seed_data`.
5. **Start API:** from `backend/`, run `python -m uvicorn app.main:app --reload --port 8000`. Open `http://localhost:8000/health`; expect `{"status":"ok",...}`.
6. **Start frontend:** from `frontend/`, run `npm install` then `npm run dev -- --host 0.0.0.0`. Open `http://localhost:5173`; use username `admin` and password from `INITIAL_ADMIN_PASSWORD` configured before first database initialization.
7. **Show inventory and forecast:** open products, select a seeded SKU, show its forecast/recommendation; explain it uses stored transaction history and the project forecast routine.
8. **Show Banker's and scheduler:** submit a safe allocation and enqueue a routine audit; explain Banker's safe sequence and that the scheduler is an in-memory demo queue.
9. **Show sale waterfall:** run safe then unsafe parallel sale scenarios. With PostgreSQL, discuss row-lock behavior; with SQLite, explicitly say the lock comparison is not demonstrated because SQLite ignores `FOR UPDATE`.
10. **Show chatbot/observability and fallback:** ask a stock question plus an out-of-scope question; open Observability and identify whether it says fallback or eBPF. If Docker, Postgres, network, or eBPF fails, use local fallback and API smoke instead; do not claim kernel telemetry or Postgres locking was active unless the status/test actually confirms it.

Fallback plan: if Docker/Postgres fails, use the SQLite fallback and skip row-lock conclusions; if no network, use preinstalled dependencies only and avoid claiming a cold install works; if eBPF fails, keep the API fallback collector and describe the missing Linux kernel/capability requirement. The fresh-tree SQLite run succeeded locally, but offline cold-start was not verified.

## Needs your decision

1. Should public self-registration stay available, or should it be restricted/disabled?
2. May startup reject missing/placeholder secrets outside development and require a persistent JWT secret plus strong initial admin/ingest secrets?
3. Should PostgreSQL connection failure fail startup rather than silently switching to SQLite?
4. **Chatbot evaluation/data decision applied:** Phase 3 corpus and held-out work completed; see [CHATBOT_EVALUATION.md](CHATBOT_EVALUATION.md). Other open issues in this report remain as previously recorded.
5. May Vite be upgraded across the major version boundary to address the current npm audit findings?

## Top five fixes before evaluation

1. Decide whether to disable/restrict public registration.
2. Replace sample secrets everywhere and approve fail-fast placeholder checks.
3. Run PostgreSQL-backed tests and the safe/unsafe concurrency demo on a working Docker/Linux engine.
4. Decide on the Vite major upgrade; address pip audit advisories after confirming fixed compatible versions.
5. Run PostgreSQL-backed tests and demo on Linux/Docker; retain the chatbot's small-sample caveat and do not present validation accuracy as real-world performance.
