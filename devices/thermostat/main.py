from __future__ import annotations

import asyncio
import random
import time
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request

from common.config import load_device_settings
from common.logging_utils import JsonLineLogger, utc_now_iso
from common.models import DeviceCommandRequest, DeviceEmitEventRequest

settings = load_device_settings()
app = FastAPI(title="Thermostat Device", version="0.1.0")
logger = JsonLineLogger(service="thermostat")
started_monotonic = time.monotonic()
request_count = 0
state: dict[str, Any] = {
    "temp": 22.0,
    "mode": "off",
    "setpoint": 22.0,
    "humidity": 45.0,
    "fan_speed": "auto",
    "sensor_health": "ok",
    "battery_pct": 96.5,
    "last_updated": utc_now_iso(),
}


def refresh_state_snapshot() -> None:
    state["humidity"] = round(min(max(state["humidity"] + random.uniform(-0.6, 0.6), 30.0), 70.0), 1)
    state["battery_pct"] = round(max(state["battery_pct"] - random.uniform(0.0, 0.02), 0.0), 2)
    state["last_updated"] = utc_now_iso()


def hvac_state() -> str:
    if state["mode"] == "off":
        return "idle"
    if state["mode"] == "heat":
        return "heating" if state["temp"] < state["setpoint"] else "idle"
    if state["mode"] == "cool":
        return "cooling" if state["temp"] > state["setpoint"] else "idle"
    return "idle"


def build_state_payload() -> dict[str, Any]:
    refresh_state_snapshot()
    payload = dict(state)
    payload["hvac_state"] = hvac_state()
    payload["recent_samples"] = [
        {"offset_s": 0, "temp": round(state["temp"], 2), "humidity": state["humidity"]},
        {"offset_s": 10, "temp": round(state["temp"] + random.uniform(-0.3, 0.3), 2), "humidity": state["humidity"]},
        {"offset_s": 20, "temp": round(state["temp"] + random.uniform(-0.3, 0.3), 2), "humidity": state["humidity"]},
    ]
    return payload


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
    await asyncio.sleep(random.uniform(0.1, 0.3))

    if command_request.action != "set_temp":
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported action for thermostat: {command_request.action}",
        )
    if command_request.value is None:
        raise HTTPException(status_code=400, detail="Thermostat action set_temp requires field 'value'")

    try:
        new_setpoint = float(command_request.value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Thermostat value must be a numeric temperature") from exc

    state["setpoint"] = round(new_setpoint, 1)
    state["temp"] = round(state["temp"] + random.uniform(-0.4, 0.4), 1)
    if state["setpoint"] > state["temp"]:
        state["mode"] = "heat"
    elif state["setpoint"] < state["temp"]:
        state["mode"] = "cool"
    else:
        state["mode"] = "off"

    payload = build_state_payload()
    processing_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "ok": True,
        "device_type": "thermostat",
        "applied_action": command_request.action,
        "new_state": payload,
        "processing_ms": processing_ms,
    }


@app.get("/state")
async def get_state() -> dict[str, Any]:
    return {"state": build_state_payload()}


@app.post("/emit_event")
async def emit_event(payload: DeviceEmitEventRequest) -> dict[str, Any]:
    hub_event_url = f"{settings.hub_url.rstrip('/')}/event"
    event_payload = {"device_id": "thermostat_1", "event": payload.event, "value": payload.value}
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

