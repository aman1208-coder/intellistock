#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [ ! -f "backend/intellistock.db" ]; then
  echo "Initializing IntelliStock database and demo seed data..."
  (cd backend && python scripts/seed_data.py)
else
  echo "Existing local database detected. Skipping reseed."
fi

echo
printf '%s\n' "==============================================================="
printf '%s\n' "🚀 IntelliStock Full-Stack System Running Live"
printf '%s\n' "==============================================================="
printf '%s\n' "🖥️  Frontend Application : http://localhost:5173"
printf '%s\n' "📚 Interactive API Docs : http://localhost:8000/docs"
printf '%s\n' "❤️  Backend Health Check : http://localhost:8000/health"
printf '%s\n' "==============================================================="
printf '%s\n' ""
printf '%s\n' "Phase 2 Evaluation Walkthrough"
printf '%s\n' "1. Sign in or register at http://localhost:5173."
printf '%s\n' "2. Click \"Demo 1: Flash Sale Race Condition\" to demonstrate DBMS row-level locking (with_for_update) vs. unsafe race overwrites."
printf '%s\n' "3. Click \"Demo 2: Warehouse Deadlock Risk\" to demonstrate Banker's Algorithm safety evaluation and 409 deadlock rejection."
printf '%s\n' "4. Click \"Demo 3: Emergency Stockout Preemption\" to demonstrate Priority Queue task preemption (Priority 1 jumping ahead of Priority 3)."
printf '%s\n' "5. Scroll to Demand Forecast to inspect the 14-day ML demand prediction, and open the bottom-right AI Chatbot to query live database stockouts."

(cd backend && python -m uvicorn app.main:app --reload --port 8000) &
BACKEND_PID=$!
(cd frontend && npm run dev -- --host 127.0.0.1 --port 5173) &
FRONTEND_PID=$!

trap 'kill $BACKEND_PID $FRONTEND_PID' EXIT

printf '%s\n' ""
printf '%s\n' "Backend and frontend processes are running in the background."
printf '%s\n' "Use Ctrl+C to stop both services."
wait
