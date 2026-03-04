from __future__ import annotations

import asyncio
import random
import time
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request

from common.config import load_device_settings
from common.logging_utils import JsonLineLogger
from common.models import DeviceCommandRequest, DeviceEmitEventRequest

settings = load_device_settings()
app = FastAPI(title="Lock Device", version="0.1.0")
logger = JsonLineLogger(service="lock")
started_monotonic = time.monotonic()
request_count = 0
state: dict[str, Any] = {"state": "locked"}


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    global request_count
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        request_count += 1
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.log(
            {
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "client_ip": request.client.host if request.client else "unknown",
                "latency_ms": latency_ms,
            }
        )


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "running",
        "uptime_seconds": int(time.monotonic() - started_monotonic),
        "request_count": request_count,
    }


@app.post("/command")
async def command(command_request: DeviceCommandRequest) -> dict[str, Any]:
    started = time.perf_counter()
    await asyncio.sleep(random.uniform(0.05, 0.15))

    if command_request.action == "lock":
        state["state"] = "locked"
    elif command_request.action == "unlock":
        state["state"] = "unlocked"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported action for lock: {command_request.action}")

    processing_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "ok": True,
        "device_type": "lock",
        "applied_action": command_request.action,
        "new_state": dict(state),
        "processing_ms": processing_ms,
    }


@app.get("/state")
async def get_state() -> dict[str, Any]:
    return {"state": dict(state)}


@app.post("/emit_event")
async def emit_event(payload: DeviceEmitEventRequest) -> dict[str, Any]:
    hub_event_url = f"{settings.hub_url.rstrip('/')}/event"
    event_payload = {"device_id": "lock_1", "event": payload.event, "value": payload.value}
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.post(hub_event_url, json=event_payload)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError) as exc:
        raise HTTPException(status_code=502, detail=f"Failed to emit event to hub: {exc.__class__.__name__}") from exc

    try:
        hub_response = response.json()
    except ValueError:
        hub_response = {"raw": response.text}
    return {"ok": response.status_code < 400, "hub_status": response.status_code, "hub_response": hub_response}

