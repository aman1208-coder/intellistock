# IntelliStock Viva Demo Guide

Project: IntelliStock - AI-Based Inventory Management System with Integrated OS & DBMS Concurrency Control

Institution: Graphic Era Deemed to be University

## 1. Overview

This Phase 2 viva presentation demonstrates how IntelliStock blends four critical layers into one operational story:

- Database concurrency safety for inventory transactions
- Operating-system deadlock avoidance and scheduling logic
- AI-driven demand forecasting for replenishment decisions
- Live web-based monitoring and human-in-the-loop operations

The platform is built with:

- FastAPI for the backend services and API layer
- PostgreSQL / SQLite-backed persistence for transactional data
- React + Vite for the frontend interface
- Tailwind-inspired utility styling with glassmorphism UI patterns
- Framer Motion for motion-rich operational dashboards

The three core pillars of the project are:

1. Concurrency control and transactional integrity
2. Resource protection and OS scheduling behavior
3. AI/ML-powered inventory intelligence and operational guidance

## 2. Presentation Flow (3-minute script)

### Opening (30–40 seconds)

"Good morning everyone. IntelliStock is an AI-based inventory management system designed to model real-world warehouse operations as a combination of database safety, operating-system coordination, and forecasting intelligence. The system uses FastAPI, a PostgreSQL/SQLite data layer, a React frontend, and motion-based UI components to make concurrency and scheduling visible in a way that is both educational and operationally realistic."

"The three core pillars of the solution are database concurrency control, deadlock avoidance in resource allocation, and AI-powered demand forecasting. Together they model the way modern logistics systems must protect data integrity, manage scarce resources, and respond to changing demand without human delay."

### Demo 1: DBMS Concurrency (45 seconds)

"In our first scenario, we show a flash sale on a low-stock inventory item. Multiple concurrent sales requests compete for the same product record. IntelliStock uses row-level locking with `SELECT ... FOR UPDATE`, which prevents the classic lost-update problem and ensures only one transaction can update the item state at a time."

"The thread waterfall in the dashboard visualizes how requests are serialized. The safe mode clearly distinguishes locked transactions from blocked ones, while the thread bars show how the system preserves data consistency. This is a direct demonstration of database concurrency control in a practical retail setting."

### Demo 2: OS Deadlock Avoidance (45 seconds)

"The next demo focuses on deadlock avoidance using Dijkstra's Banker's Algorithm. We simulate warehouse resource allocation across multiple resource classes: capacity, dock bays, and equipment. Instead of waiting until a system stalls, the scheduler evaluates whether the requested allocation leaves the system in a safe state."

"If the request would push the warehouse into an unsafe condition, the system rejects it with a deadlock warning and an HTTP 409 response. The Banker's Lab shows the available and maximum claims side by side, making it clear why the system chooses to deny the unsafe allocation instead of allowing deadlock to occur."

### Demo 3: OS Priority Scheduling (45 seconds)

"This demo highlights priority scheduling in the operating-system layer. The queue ensures non-preemptive priority-based ordering, where urgent inventory checks and emergency replenishment tasks are advanced ahead of routine audits."

"A stockout preemption scenario shows Priority 1 work jumping ahead of Priority 3 tasks. This visual demonstrates how the system prioritizes critical fulfillment work while still maintaining a predictable scheduling model."

### Demo 4: AI/ML Forecasting and Assistant (45 seconds)

"Finally, we show the AI layer. IntelliStock uses a 14-day ridge regression demand forecast to predict future consumption and dynamically calculate the reorder point. This allows the system to trigger inventory actions before stockouts occur and keep the warehouse responsive under changing demand."

"The live AI stock chat assistant answers natural-language questions about zero-stock products, warehouse thresholds, pending reorders, and service capacity. This closes the loop between system state, operational decisions, and human interaction, making IntelliStock useful as both a simulation and a practical inventory dashboard."

## 3. Demo Sequence Summary

### Demo 1 - DBMS Concurrency
- Flash sale race condition simulation
- Row-level locking with `with_for_update`
- Lost-update prevention
- Thread waterfall visualization of serialized transactions

### Demo 2 - OS Deadlock Avoidance
- Resource set: Capacity, Dock Bays, Equipment
- Banker's Algorithm evaluation
- Unsafe allocation rejection
- HTTP 409 deadlock-prevention response

### Demo 3 - OS Priority Scheduling
- Priority queue visualization
- Emergency stockout preemption
- Priority 1 jump ahead of Priority 3 tasks
- Queue movement and scheduler demonstration

### Demo 4 - AI/ML Forecasting
- 14-day ridge regression demand forecast
- Dynamic reorder point calculation
- Live natural-language inventory chatbot
- AI-informed replenishment recommendations

## 4. Local Run Commands

### Backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm run dev
```

## 5. Suggested Closing Statement

"IntelliStock demonstrates that inventory management is not just a business problem, but a system design problem. It combines database safety, operating-system resource management, and AI forecasting to create a realistic, interactive demonstration of how modern warehouse intelligence can protect data, prevent deadlock, prioritize urgency, and support faster decision-making."
