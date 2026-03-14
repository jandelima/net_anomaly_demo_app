from __future__ import annotations

import hashlib
import json
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Annotated

import httpx
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.wsgi import WSGIMiddleware

from common.config import HubSettings, load_hub_settings
from common.logging_utils import JsonLineLogger, utc_now_iso
from common.models import HubCommandRequest, HubEventRequest
from common.rate_limit import InMemoryRateLimiter
from common.request_feature_logger import (
    CsvRequestFeatureLogger,
    build_request_preview,
    extract_primary_query_value,
    shannon_entropy,
)
from common.validation import validate_command_for_device
from hub.demo_flask import create_demo_app


@dataclass
class HubCounters:
    total_requests: int = 0
    commands_received: int = 0
    states_queried: int = 0
    events_received: int = 0
    firmware_uploads: int = 0


@dataclass
class HubRuntimeState:
    started_monotonic: float
    counters: HubCounters
    recent_events: deque[dict[str, Any]]


settings: HubSettings = load_hub_settings()
logger = JsonLineLogger(
    service="hub",
    log_to_file=settings.log_to_file,
    file_path=settings.log_file_path if settings.log_to_file else None,
)
app_feature_logger = CsvRequestFeatureLogger(settings.data_dir / "app_level" / "hub_requests.csv")
rate_limiter = InMemoryRateLimiter(settings.rate_limit_rpm) if settings.rate_limit_enabled else None
runtime = HubRuntimeState(
    started_monotonic=time.monotonic(),
    counters=HubCounters(),
    recent_events=deque(maxlen=200),
)


def demo_search_records(query: str) -> dict[str, Any]:
    normalized = query.strip().lower()

    matching_devices: list[dict[str, str]] = []
    for device_id, base_url in settings.device_urls.items():
        searchable = f"{device_id} {base_url}".lower()
        if not normalized or normalized in searchable:
            matching_devices.append({"device_id": device_id, "base_url": base_url})

    matching_events: list[dict[str, Any]] = []
    for event in reversed(runtime.recent_events):
        serialized = json.dumps(event, ensure_ascii=True).lower()
        if not normalized or normalized in serialized:
            matching_events.append(event)
        if len(matching_events) >= 20:
            break

    return {
        "query": query,
        "matched_devices": matching_devices,
        "matched_events": matching_events,
        "total_matched_events": len(matching_events),
    }


def get_device_record(device_id: str) -> dict[str, Any]:
    device_record = settings.device_inventory.get(device_id)
    if device_record is None:
        raise HTTPException(status_code=400, detail=f"Unknown device_id: {device_id}")
    return device_record


app = FastAPI(title="Smart Home Hub PoC", version=settings.version)
legacy_search_demo_app = create_demo_app(demo_search_records)
app.mount("/demo", WSGIMiddleware(legacy_search_demo_app))


@app.on_event("startup")
async def on_startup() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    app.state.http_client = httpx.AsyncClient(timeout=settings.request_timeout_seconds)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    client: httpx.AsyncClient = app.state.http_client
    await client.aclose()


def get_client_ip(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def require_api_key(x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing X-API-Key")


def apply_rate_limit(request: Request) -> None:
    if not settings.rate_limit_enabled or rate_limiter is None:
        return
    client_ip = get_client_ip(request)
    if not rate_limiter.allow(client_ip):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: max {settings.rate_limit_rpm} requests per minute",
        )


async def forward_request(
    request: Request,
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
) -> tuple[float, dict[str, Any]]:
    client: httpx.AsyncClient = request.app.state.http_client
    started = time.perf_counter()
    request_kwargs: dict[str, Any] = {}
    if payload is not None:
        if method.upper() == "GET":
            request_kwargs["params"] = payload
        else:
            request_kwargs["json"] = payload
    try:
        response = await client.request(method=method, url=url, **request_kwargs)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Device offline or timeout while calling {url}: {exc.__class__.__name__}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Device request failed for {url}: {str(exc)}") from exc

    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Device returned error status {response.status_code} from {url}",
        )
    try:
        device_json = response.json()
    except ValueError:
        device_json = {"raw": response.text}
    return latency_ms, device_json


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    started = time.perf_counter()
    timestamp_ms = int(time.time() * 1000)
    body_data: dict[str, Any] = {}
    is_multipart = "multipart/form-data" in request.headers.get("content-type", "").lower()
    response = None
    if request.method == "POST" and request.url.path in {"/command", "/event"}:
        try:
            parsed = await request.json()
            if isinstance(parsed, dict):
                body_data = parsed
        except (json.JSONDecodeError, UnicodeDecodeError):
            body_data = {}

    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        runtime.counters.total_requests += 1
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        payload: dict[str, Any] = {
            "method": request.method,
            "path": request.url.path,
            "status_code": status_code,
            "client_ip": get_client_ip(request),
            "latency_ms": latency_ms,
        }
        if request.url.path == "/command":
            request_id = body_data.get("request_id")
            if request_id:
                payload["request_id"] = request_id
            if "device_id" in body_data:
                payload["device_id"] = body_data["device_id"]
            if "action" in body_data:
                payload["action"] = body_data["action"]
        if request.url.path == "/state":
            device_id = request.query_params.get("device_id")
            if device_id:
                payload["device_id"] = device_id
        logger.log(payload)
        try:
            query = request.url.query
            primary_query_value = extract_primary_query_value(request.url.path, query)
            request_content_length = int(request.headers.get("content-length", "0") or "0")
            response_length_header = response.headers.get("content-length") if response is not None else None
            if response_length_header is not None:
                response_length = int(response_length_header)
            else:
                response_body = getattr(response, "body", b"") if response is not None else b""
                response_length = len(response_body or b"")
            app_feature_logger.log(
                {
                    "timestamp_ms": timestamp_ms,
                    "is_error": int(status_code >= 400),
                    "is_auth_failure": int(status_code == 401),
                    "path": request.url.path,
                    "query_length": len(primary_query_value),
                    "query_entropy": shannon_entropy(primary_query_value),
                    "request_content_length": request_content_length,
                    "response_length": response_length,
                    "request_preview": build_request_preview(
                        method=request.method,
                        path=request.url.path,
                        query=query,
                        body_data=body_data,
                        is_multipart=is_multipart,
                    ),
                }
            )
        except Exception:
            pass


@app.get("/health")
async def health() -> dict[str, Any]:
    uptime_seconds = int(time.monotonic() - runtime.started_monotonic)
    return {
        "status": "running",
        "version": settings.version,
        "uptime_seconds": uptime_seconds,
        "counters": {
            "total_requests": runtime.counters.total_requests,
            "commands_received": runtime.counters.commands_received,
            "states_queried": runtime.counters.states_queried,
            "events_received": runtime.counters.events_received,
            "firmware_uploads": runtime.counters.firmware_uploads,
        },
    }


@app.post("/command")
async def command(
    command_request: HubCommandRequest,
    request: Request,
    _: None = Depends(require_api_key),
    __: None = Depends(apply_rate_limit),
) -> dict[str, Any]:
    runtime.counters.commands_received += 1
    validation_error = validate_command_for_device(
        settings.device_inventory,
        command_request.device_id,
        command_request.action,
    )
    if validation_error is not None:
        raise HTTPException(status_code=400, detail=validation_error)

    if command_request.action == "set_temp" and command_request.value is None:
        raise HTTPException(status_code=400, detail="Field 'value' is required for action 'set_temp'")

    device_record = get_device_record(command_request.device_id)
    device_url = device_record["base_url"]
    forwarded_to = f"{device_url}/command"
    body: dict[str, Any] = {"device_id": command_request.device_id, "action": command_request.action}
    if command_request.value is not None:
        body["value"] = command_request.value

    latency_ms, device_response = await forward_request(request, "POST", forwarded_to, body)
    return {
        "ok": True,
        "device_id": command_request.device_id,
        "action": command_request.action,
        "forwarded_to": forwarded_to,
        "device_response": device_response,
        "hub_latency_ms": latency_ms,
    }


@app.get("/state")
async def state(
    request: Request,
    device_id: str = Query(..., min_length=1),
    _: None = Depends(require_api_key),
    __: None = Depends(apply_rate_limit),
) -> dict[str, Any]:
    runtime.counters.states_queried += 1
    device_record = get_device_record(device_id)
    forwarded_to = f"{device_record['base_url']}/state"
    payload = {"device_id": device_id}
    latency_ms, device_state = await forward_request(request, "GET", forwarded_to, payload)
    return {
        "ok": True,
        "device_id": device_id,
        "forwarded_to": forwarded_to,
        "device_state": device_state,
        "hub_latency_ms": latency_ms,
    }


@app.post("/event")
async def event(event_request: HubEventRequest) -> dict[str, Any]:
    runtime.counters.events_received += 1
    event_ts = event_request.ts or utc_now_iso()
    event_record = {
        "device_id": event_request.device_id,
        "event": event_request.event,
        "value": event_request.value,
        "ts": event_ts,
    }
    runtime.recent_events.append(event_record)
    return {"ok": True}


@app.get("/events")
async def events(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    most_recent = list(reversed(runtime.recent_events))[:limit]
    return {"events": most_recent}


@app.post("/firmware")
async def firmware(
    file: UploadFile = File(...),
    _: None = Depends(require_api_key),
) -> dict[str, Any]:
    runtime.counters.firmware_uploads += 1
    settings.firmware_dir.mkdir(parents=True, exist_ok=True)

    original_name = Path(file.filename or "firmware.bin").name
    destination = settings.firmware_dir / original_name

    sha256 = hashlib.sha256()
    size_bytes = 0
    with destination.open("wb") as output:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
            sha256.update(chunk)
            size_bytes += len(chunk)
    await file.close()

    return {
        "filename": original_name,
        "size_bytes": size_bytes,
        "sha256": sha256.hexdigest(),
        "saved_path": str(destination),
    }
