# Smart Home Hub PoC Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a lightweight Smart Home Hub PoC with a FastAPI hub and three simulated FastAPI devices for anomaly-detection demo traffic.

**Architecture:** A central hub service proxies commands/state queries to local device services via HTTP with short timeouts and clear error handling. Shared logic (config, models, structured JSON logging, rate limiting) lives in `common/`. State is in-memory and firmware/log files are written only under `./data`.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, httpx, python-multipart, pytest.

### Task 1: Repository Skeleton

**Files:**
- Create: `hub/`, `devices/light/`, `devices/lock/`, `devices/thermostat/`, `common/`, `docker/`, `tests/`

**Step 1: Create package structure**
Create all required directories and `__init__.py` files.

**Step 2: Add shared utilities**
Implement environment config, shared pydantic models, JSON-line logger, and in-memory rate limiter.

### Task 2: Hub API

**Files:**
- Create: `hub/main.py`

**Step 1: Implement health/counters/event storage**
Create in-memory counters, uptime, and rolling events (max 200).

**Step 2: Implement authenticated endpoints**
Add `/command`, `/state`, `/firmware` with `X-API-Key` auth and optional rate limit.

**Step 3: Implement public endpoints**
Add `/health`, `/event`, `/events`.

**Step 4: Add middleware logging**
Log one JSON line per request with latency and contextual fields.

### Task 3: Devices

**Files:**
- Create: `devices/light/main.py`
- Create: `devices/lock/main.py`
- Create: `devices/thermostat/main.py`

**Step 1: Implement core endpoints**
Add `/health`, `/command`, `/state` with in-memory state.

**Step 2: Implement emit_event**
Add `/emit_event` for posting events to hub.

**Step 3: Add per-device behavior**
Apply delays and payload richness according to requirements.

### Task 4: Runtime Artifacts

**Files:**
- Create: `requirements.txt`
- Create: `docker/Dockerfile`
- Create: `docker/docker-compose.yml`
- Create: `README.md`

**Step 1: Add native run instructions**
Document venv setup and uvicorn commands.

**Step 2: Add docker instructions**
Document compose build/run and mapped ports.

**Step 3: Add curl examples**
Document all requested endpoint examples including firmware upload.

### Task 5: Verification

**Files:**
- Test: `tests/test_rate_limit_and_validation.py`

**Step 1: RED**
Run tests and verify initial failure.

**Step 2: GREEN**
Implement minimal code to pass tests.

**Step 3: Full verification**
Run tests and Python compile checks before completion.
