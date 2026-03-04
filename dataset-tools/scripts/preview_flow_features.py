#!/usr/bin/env python3
"""Generate normal traffic for 1 minute and preview NFStream flow features.

This script runs an end-to-end pipeline:
1) Capture local traffic with tcpdump into a PCAP file.
2) Generate realistic Smart Home Hub traffic concurrently.
3) Parse the PCAP with NFStream.
4) Save all available NFStream flow features to CSV.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import shutil
import signal
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
from nfstream import NFStreamer


VALID_DEVICES = ("light_1", "lock_1", "thermostat_1")
EVENTS = ("motion_detected", "door_opened", "heartbeat", "temperature_update")


@dataclass
class TrafficMetrics:
    total_requests: int = 0
    errors_total: int = 0
    endpoint_counts: Counter[str] = field(default_factory=Counter)
    status_counts: Counter[str] = field(default_factory=Counter)

    def record(self, endpoint: str, status_code: int | None) -> None:
        self.total_requests += 1
        self.endpoint_counts[endpoint] += 1
        if status_code is None:
            self.errors_total += 1
            self.status_counts["error"] += 1
            return
        key = str(status_code)
        self.status_counts[key] += 1
        if status_code >= 400:
            self.errors_total += 1


def build_command_payload() -> dict[str, Any]:
    device = random.choice(VALID_DEVICES)
    if device == "light_1":
        action = random.choice(("turn_on", "turn_off"))
        return {"device_id": device, "action": action}
    if device == "lock_1":
        action = random.choice(("lock", "unlock"))
        return {"device_id": device, "action": action}

    temp = round(random.uniform(18.0, 26.0), 1)
    return {"device_id": "thermostat_1", "action": "set_temp", "value": temp}


def pick_operation() -> str:
    value = random.random()
    if value < 0.70:
        return "command"
    if value < 0.90:
        return "state"
    if value < 0.98:
        return "event"
    return "firmware"


async def do_request(client: httpx.AsyncClient, hub_url: str, api_key: str, operation: str) -> int | None:
    try:
        if operation == "command":
            payload = build_command_payload()
            response = await client.post(
                f"{hub_url}/command",
                json=payload,
                headers={"X-API-Key": api_key},
            )
            return response.status_code

        if operation == "state":
            device = random.choice(VALID_DEVICES)
            response = await client.get(
                f"{hub_url}/state",
                params={"device_id": device},
                headers={"X-API-Key": api_key},
            )
            return response.status_code

        if operation == "event":
            payload = {
                "device_id": random.choice(VALID_DEVICES),
                "event": random.choice(EVENTS),
                "value": random.randint(0, 100),
            }
            response = await client.post(f"{hub_url}/event", json=payload)
            return response.status_code

        firmware_size = random.randint(1024, 10 * 1024)
        firmware_content = os.urandom(firmware_size)
        response = await client.post(
            f"{hub_url}/firmware",
            headers={"X-API-Key": api_key},
            files={"file": ("demo_firmware.bin", firmware_content, "application/octet-stream")},
        )
        return response.status_code

    except httpx.HTTPError:
        return None


async def worker_loop(
    worker_id: int,
    client: httpx.AsyncClient,
    hub_url: str,
    api_key: str,
    stop_at: float,
    metrics: TrafficMetrics,
) -> None:
    del worker_id
    while time.monotonic() < stop_at:
        operation = pick_operation()
        endpoint = f"/{operation}"
        status_code = await do_request(client, hub_url, api_key, operation)
        metrics.record(endpoint, status_code)
        await asyncio.sleep(random.uniform(0.1, 1.5))


async def generate_traffic(hub_url: str, api_key: str, duration: int, workers: int) -> tuple[TrafficMetrics, float]:
    metrics = TrafficMetrics()
    started = time.monotonic()
    stop_at = started + duration

    async with httpx.AsyncClient(timeout=2.0) as client:
        tasks = [
            asyncio.create_task(worker_loop(index, client, hub_url, api_key, stop_at, metrics))
            for index in range(workers)
        ]
        await asyncio.gather(*tasks)

    elapsed = time.monotonic() - started
    return metrics, elapsed


def build_filter_expression(ports_spec: str) -> str:
    tokens = [item.strip() for item in ports_spec.split(",") if item.strip()]
    if not tokens:
        return "tcp"

    clauses: list[str] = []
    for token in tokens:
        if "-" in token:
            start_raw, end_raw = token.split("-", 1)
            start = int(start_raw.strip())
            end = int(end_raw.strip())
            if start <= 0 or end <= 0 or start > 65535 or end > 65535 or start > end:
                raise ValueError(f"Faixa de porta invalida: {token}")
            clauses.append(f"portrange {start}-{end}")
            continue

        port = int(token)
        if port <= 0 or port > 65535:
            raise ValueError(f"Porta invalida: {token}")
        clauses.append(f"port {port}")
    return " or ".join(clauses)


def start_tcpdump(interface: str, filter_expression: str, pcap_path: Path) -> subprocess.Popen[str]:
    tcpdump_bin = shutil.which("tcpdump")
    if tcpdump_bin is None:
        raise RuntimeError("tcpdump nao encontrado no PATH. Instale tcpdump antes de continuar.")

    cmd = [tcpdump_bin, "-i", interface, "-U", "-w", str(pcap_path), filter_expression]
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    time.sleep(1.0)

    if process.poll() is not None:
        stderr = process.stderr.read() if process.stderr else ""
        raise RuntimeError(
            "Falha ao iniciar tcpdump. Rode com sudo ou ajuste permissoes de captura.\n"
            f"Comando: {' '.join(cmd)}\n"
            f"Erro: {stderr.strip()}"
        )
    return process


def stop_tcpdump(process: subprocess.Popen[str]) -> str:
    if process.poll() is not None:
        return (process.stderr.read().strip() if process.stderr else "")
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=3)
    return (process.stderr.read().strip() if process.stderr else "")


def extract_flow_features(pcap_path: Path, csv_path: Path) -> tuple[pd.DataFrame, list[str]]:
    streamer = NFStreamer(source=str(pcap_path))
    df = streamer.to_pandas()
    df.to_csv(csv_path, index=False)
    return df, list(df.columns)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview de features NFStream com 1 minuto de trafego.")
    parser.add_argument("--hub-url", default="http://localhost:8000", help="URL base do hub")
    parser.add_argument("--api-key", default="devkey", help="Valor do header X-API-Key")
    parser.add_argument("--duration", type=int, default=60, help="Duracao da geracao de trafego em segundos")
    parser.add_argument("--workers", type=int, default=6, help="Quantidade de workers concorrentes")
    parser.add_argument("--interface", default="lo", help="Interface de captura (ex: lo)")
    parser.add_argument(
        "--ports",
        default="8000,8001,8002,8003",
        help="Portas para filtro BPF. Aceita lista e faixa, ex: 8000,8001,8002 ou 8000-9000",
    )
    parser.add_argument(
        "--pcap-out",
        default="dataset-tools/output/traffic_preview.pcap",
        help="Caminho do pcap de saida",
    )
    parser.add_argument(
        "--csv-out",
        default="dataset-tools/output/flow_features_preview.csv",
        help="Caminho do csv de flows",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    hub_url = args.hub_url.rstrip("/")
    try:
        filter_expression = build_filter_expression(args.ports)
    except ValueError as exc:
        print(f"Erro no argumento --ports: {exc}", file=sys.stderr)
        return 1
    pcap_path = Path(args.pcap_out)
    csv_path = Path(args.csv_out)
    pcap_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    print("[1/4] Iniciando captura com tcpdump...")
    try:
        capture_process = start_tcpdump(args.interface, filter_expression, pcap_path)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print("[2/4] Gerando trafego normal...")
    try:
        metrics, elapsed = asyncio.run(generate_traffic(hub_url, args.api_key, args.duration, args.workers))
    finally:
        print("[3/4] Finalizando captura...")
        tcpdump_stderr = stop_tcpdump(capture_process)

    if not pcap_path.exists():
        print(
            "Erro: o arquivo PCAP nao foi gerado. "
            "Revise o filtro --ports e as permissoes do tcpdump.",
            file=sys.stderr,
        )
        if tcpdump_stderr:
            print(f"tcpdump stderr:\n{tcpdump_stderr}", file=sys.stderr)
        return 1
    if pcap_path.stat().st_size == 0:
        print(
            "Erro: PCAP gerado com 0 bytes. "
            "Verifique se houve trafego e se a interface/filtro estao corretos.",
            file=sys.stderr,
        )
        if tcpdump_stderr:
            print(f"tcpdump stderr:\n{tcpdump_stderr}", file=sys.stderr)
        return 1

    print("[4/4] Extraindo flows com NFStream...")
    try:
        df, columns = extract_flow_features(pcap_path, csv_path)
    except Exception as exc:
        print(f"Erro ao processar PCAP com NFStream: {exc}", file=sys.stderr)
        return 1

    rps = metrics.total_requests / elapsed if elapsed > 0 else 0.0
    print("\n=== Resumo de Trafego ===")
    print(f"Duracao real: {elapsed:.2f}s")
    print(f"Total requests: {metrics.total_requests}")
    print(f"Errors total: {metrics.errors_total}")
    print(f"Media req/s: {rps:.2f}")
    print("Requests por endpoint:")
    for endpoint, count in sorted(metrics.endpoint_counts.items()):
        print(f"  {endpoint}: {count}")

    print("\n=== Resumo NFStream ===")
    print(f"Flows processados: {len(df)}")
    print(f"CSV gerado: {csv_path}")
    print(f"Total de colunas NFStream: {len(columns)}")
    if columns:
        print("Primeiras colunas:")
        for name in columns[:25]:
            print(f"  - {name}")

    if not df.empty:
        print("\nExemplo (primeiras 3 linhas):")
        print(df.head(3).to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
