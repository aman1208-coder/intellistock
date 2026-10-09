@echo off
setlocal enabledelayedexpansion
set "ROOT=%~dp0"
cd /d "%ROOT%"

if not exist "backend\intellistock.db" (
    echo Initializing IntelliStock database and demo seed data...
    cd backend
    python scripts/seed_data.py
    cd /d "%ROOT%"
) else (
    echo Existing local database detected. Skipping reseed.
)

echo.
echo ==============================================================
echo 🚀 IntelliStock Full-Stack System Running Live
echo ==============================================================
echo 🖥️  Frontend Application : http://localhost:5173
echo 📚 Interactive API Docs : http://localhost:8000/docs
echo ❤️  Backend Health Check : http://localhost:8000/health
echo ==============================================================
echo.
echo Phase 2 Evaluation Walkthrough
echo 1. Sign in or register at http://localhost:5173.
echo 2. Click "Demo 1: Flash Sale Race Condition" to demonstrate DBMS row-level locking (with_for_update) vs. unsafe race overwrites.
echo 3. Click "Demo 2: Warehouse Deadlock Risk" to demonstrate Banker's Algorithm safety evaluation and 409 deadlock rejection.
echo 4. Click "Demo 3: Emergency Stockout Preemption" to demonstrate Priority Queue task preemption (Priority 1 jumping ahead of Priority 3).
echo 5. Scroll to Demand Forecast to inspect the 14-day ML demand prediction, and open the bottom-right AI Chatbot to query live database stockouts.

echo.
start "IntelliStock Backend" cmd /k "cd /d ^"%ROOT%backend^" && python -m uvicorn app.main:app --reload --port 8000"
start "IntelliStock Frontend" cmd /k "cd /d ^"%ROOT%frontend^" && npm run dev -- --host 127.0.0.1 --port 5173"

echo Backend and frontend processes started in separate windows.
echo.
echo Press any key to close this launcher window when finished.
pause >nul
