#!/usr/bin/env python3
"""Generate benign hub traffic without capture or flow extraction."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.config import build_device_inventory


@dataclass(frozen=True)
class ModeSpec:
    weight: float
    duration_range_seconds: tuple[float, float]
    interval_range_seconds: tuple[float, float] | None


@dataclass(frozen=True)
class RequestSpec:
    method: str
    path: str
    headers: dict[str, str]
    params: dict[str, Any]
    json_body: dict[str, Any] | None
    multipart_fields: list[tuple[str, tuple[None, str] | tuple[str, bytes, str]]] | None


@dataclass
class RunMetrics:
    total_requests: int = 0
    network_errors: int = 0
    path_counts: Counter[str] = None
    mode_counts: Counter[str] = None
    status_family_counts: Counter[str] = None

    def __post_init__(self) -> None:
        self.path_counts = Counter()
        self.mode_counts = Counter()
        self.status_family_counts = Counter()


MODE_SPECS: dict[str, ModeSpec] = {
    "idle": ModeSpec(weight=0.20, duration_range_seconds=(12.0, 45.0), interval_range_seconds=None),
    "sparse": ModeSpec(weight=0.25, duration_range_seconds=(20.0, 90.0), interval_range_seconds=(8.0, 25.0)),
    "normal": ModeSpec(weight=0.45, duration_range_seconds=(30.0, 180.0), interval_range_seconds=(1.5, 4.0)),
    "busy": ModeSpec(weight=0.10, duration_range_seconds=(8.0, 30.0), interval_range_seconds=(0.2, 1.2)),
}

ENDPOINT_WEIGHTS: dict[str, float] = {
    "/command": 0.38,
    "/state": 0.24,
    "/health": 0.12,
    "/event": 0.08,
    "/events": 0.06,
    "/firmware": 0.02,
    "/demo/search": 0.07,
    "/demo/upload-preview": 0.03,
}

DEVICE_INVENTORY = build_device_inventory()
DEVICE_IDS = tuple(DEVICE_INVENTORY.keys())
SEARCH_QUERY_WHITELIST = (
    "light_1",
    "light_10",
    "lock_1",
    "lock_6",
    "thermostat_1",
    "thermostat_4",
    "heartbeat",
    "motion_detected",
    "door_opened",
    "temperature_update",
)
UPLOAD_NOTES = (
    "coleta_manual",
    "validacao_formulario",
    "checagem_upload",
    "registro_diagnostico",
)
EVENT_NAMES_BY_TYPE: dict[str, tuple[str, ...]] = {
    "light": ("heartbeat", "motion_detected"),
    "lock": ("heartbeat", "door_opened"),
    "thermostat": ("heartbeat", "temperature_update"),
}
AUTHENTICATED_PATHS = {"/command", "/state", "/firmware"}


def weighted_choice(rng: Random, weighted_values: dict[str, float]) -> str:
    threshold = rng.random()
    running_total = 0.0
    last_key = next(iter(weighted_values))
    for key, weight in weighted_values.items():
        running_total += weight
        last_key = key
        if threshold <= running_total:
            return key
    return last_key


def sample_mode(rng: Random) -> str:
    return weighted_choice(rng, {name: spec.weight for name, spec in MODE_SPECS.items()})


def sample_duration_seconds(rng: Random, mode_name: str) -> float:
    low, high = MODE_SPECS[mode_name].duration_range_seconds
    return rng.uniform(low, high)


def sample_interval_seconds(rng: Random, mode_name: str) -> float:
    interval_range = MODE_SPECS[mode_name].interval_range_seconds
    if interval_range is None:
        return 0.0
    low, high = interval_range
    return rng.uniform(low, high)


def build_request_spec(
    rng: Random,
    endpoint: str | None = None,
    api_key: str = "devkey",
) -> RequestSpec:
    path = endpoint or weighted_choice(rng, ENDPOINT_WEIGHTS)
    headers = {"X-API-Key": api_key} if path in AUTHENTICATED_PATHS else {}

    if path == "/health":
        return RequestSpec("GET", path, headers, {}, None, None)

    if path == "/command":
        device_id = rng.choice(DEVICE_IDS)
        device_type = DEVICE_INVENTORY[device_id]["type"]
        if device_type == "light":
            action = rng.choice(("turn_on", "turn_off"))
            body: dict[str, Any] = {"device_id": device_id, "action": action}
        elif device_type == "lock":
            action = rng.choice(("lock", "unlock"))
            body = {"device_id": device_id, "action": action}
        else:
            temp = round(rng.uniform(18.0, 26.0), 1)
            body = {"device_id": device_id, "action": "set_temp", "value": temp}
        body["request_id"] = f"benign-{int(time.time() * 1000)}"
        return RequestSpec("POST", path, headers, {}, body, None)

    if path == "/state":
        device_id = rng.choice(DEVICE_IDS)
        return RequestSpec("GET", path, headers, {"device_id": device_id}, None, None)

    if path == "/event":
        device_id = rng.choice(DEVICE_IDS)
        device_type = DEVICE_INVENTORY[device_id]["type"]
        event_name = rng.choice(EVENT_NAMES_BY_TYPE[device_type])
        if event_name == "temperature_update":
            value = {"temp": round(rng.uniform(18.0, 26.0), 1)}
        elif event_name == "motion_detected":
            value = {"zone": rng.choice(("entry", "kitchen", "garage"))}
        elif event_name == "door_opened":
            value = {"source": rng.choice(("manual_test", "routine_check"))}
        else:
            value = {"ok": True}
        return RequestSpec(
            "POST",
            path,
            headers,
            {},
            {"device_id": device_id, "event": event_name, "value": value},
            None,
        )

    if path == "/events":
        limit = weighted_choice(rng, {"10": 0.60, "20": 0.30, "50": 0.10})
        return RequestSpec("GET", path, headers, {"limit": int(limit)}, None, None)

    if path == "/firmware":
        size = rng.randint(1024, 4096)
        seed_bytes = b"firmware-preview\n"
        content = (seed_bytes * ((size // len(seed_bytes)) + 1))[:size]
        multipart_fields = [
            ("file", ("firmware_preview.bin", content, "application/octet-stream")),
        ]
        return RequestSpec("POST", path, headers, {}, None, multipart_fields)

    if path == "/demo/search":
        query = rng.choice(SEARCH_QUERY_WHITELIST)
        return RequestSpec("GET", path, headers, {"q": query}, None, None)

    if path == "/demo/upload-preview":
        device_id = rng.choice(DEVICE_IDS)
        ticket = f"SUP-{rng.randint(1000, 9999)}"
        note = rng.choice(UPLOAD_NOTES)
        multipart_fields: list[tuple[str, tuple[None, str] | tuple[str, bytes, str]]] = [
            ("device_id", (None, device_id)),
            ("ticket", (None, ticket)),
            ("note", (None, note)),
        ]
        if rng.random() < 0.20:
            attachment_size = rng.randint(64, 512)
            attachment_text = (f"diagnostic for {device_id}\n".encode("utf-8") * 32)[:attachment_size]
            multipart_fields.append(("attachment", ("diag.txt", attachment_text, "text/plain")))
        return RequestSpec("POST", path, headers, {}, None, multipart_fields)

    raise ValueError(f"Unsupported endpoint: {path}")


async def send_request(client: httpx.AsyncClient, hub_url: str, request_spec: RequestSpec) -> int:
    response = await client.request(
        method=request_spec.method,
        url=f"{hub_url.rstrip('/')}{request_spec.path}",
        headers=request_spec.headers,
        params=request_spec.params,
        json=request_spec.json_body,
        files=request_spec.multipart_fields,
    )
    return response.status_code


async def run_benign_traffic(
    hub_url: str,
    api_key: str,
    duration_seconds: int,
    request_timeout_seconds: float,
    seed: int | None,
) -> RunMetrics:
    rng = Random(seed)
    metrics = RunMetrics()
    stop_at = time.monotonic() + duration_seconds

    async with httpx.AsyncClient(timeout=request_timeout_seconds) as client:
        healthcheck = await client.get(f"{hub_url.rstrip('/')}/health")
        healthcheck.raise_for_status()

        while time.monotonic() < stop_at:
            mode_name = sample_mode(rng)
            metrics.mode_counts[mode_name] += 1
            mode_duration = sample_duration_seconds(rng, mode_name)
            mode_stop_at = min(stop_at, time.monotonic() + mode_duration)

            if mode_name == "idle":
                await asyncio.sleep(max(0.0, mode_stop_at - time.monotonic()))
                continue

            while time.monotonic() < mode_stop_at:
                request_spec = build_request_spec(rng, api_key=api_key)
                metrics.total_requests += 1
                metrics.path_counts[request_spec.path] += 1
                try:
                    status_code = await send_request(client, hub_url, request_spec)
                except httpx.HTTPError:
                    metrics.network_errors += 1
                else:
                    metrics.status_family_counts[f"{status_code // 100}xx"] += 1

                next_interval = sample_interval_seconds(rng, mode_name)
                if time.monotonic() + next_interval > mode_stop_at:
                    break
                await asyncio.sleep(next_interval)

    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate benign traffic against the hub only.")
    parser.add_argument("--hub-url", default="http://localhost:8000")
    parser.add_argument("--api-key", default="devkey")
    parser.add_argument("--duration-seconds", type=int, default=3600)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--request-timeout-seconds", type=float, default=5.0)
    return parser.parse_args()


def print_summary(metrics: RunMetrics, elapsed_seconds: float) -> None:
    print("=== Benign Traffic Summary ===")
    print(f"Elapsed seconds: {elapsed_seconds:.2f}")
    print(f"Total requests: {metrics.total_requests}")
    print(f"Network errors: {metrics.network_errors}")
    print("Requests by path:")
    for path, count in sorted(metrics.path_counts.items()):
        print(f"  {path}: {count}")
    print("Mode counts:")
    for mode_name, count in sorted(metrics.mode_counts.items()):
        print(f"  {mode_name}: {count}")
    print("HTTP status families:")
    for family, count in sorted(metrics.status_family_counts.items()):
        print(f"  {family}: {count}")


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    try:
        metrics = asyncio.run(
            run_benign_traffic(
                hub_url=args.hub_url,
                api_key=args.api_key,
                duration_seconds=args.duration_seconds,
                request_timeout_seconds=args.request_timeout_seconds,
                seed=args.seed,
            )
        )
    except httpx.HTTPError as exc:
        print(f"Startup healthcheck failed: {exc}")
        return 1

    print_summary(metrics, time.monotonic() - started)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
