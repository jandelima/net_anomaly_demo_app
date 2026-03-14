#!/usr/bin/env python3
"""Orchestrate benign traffic capture and NFStream extraction."""

from __future__ import annotations

import argparse
import json
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture benign traffic and extract NFStream flow features.")
    parser.add_argument("--hub-url", default="http://localhost:8000")
    parser.add_argument("--api-key", default="devkey")
    parser.add_argument("--duration-seconds", type=int, default=3600)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--request-timeout-seconds", type=float, default=5.0)
    parser.add_argument("--interface", default="lo")
    parser.add_argument("--port-range-start", type=int, default=8000)
    parser.add_argument("--port-range-end", type=int, default=9000)
    parser.add_argument("--output-dir", default="dataset-tools/output/benign_runs")
    return parser.parse_args(argv)


def build_tcpdump_filter(port_range_start: int, port_range_end: int) -> str:
    if port_range_start <= 0 or port_range_end <= 0:
        raise ValueError("Port range values must be positive")
    if port_range_start > 65535 or port_range_end > 65535:
        raise ValueError("Port range values must be <= 65535")
    if port_range_start > port_range_end:
        raise ValueError("port_range_start cannot be greater than port_range_end")
    return f"tcp portrange {port_range_start}-{port_range_end}"


def ensure_hub_healthy(hub_url: str, timeout_seconds: float = 5.0) -> None:
    response = httpx.get(f"{hub_url.rstrip('/')}/health", timeout=timeout_seconds)
    response.raise_for_status()


def ensure_tcpdump_available() -> str:
    tcpdump_bin = shutil.which("tcpdump")
    if tcpdump_bin is None:
        raise RuntimeError("tcpdump nao encontrado no PATH. Instale tcpdump antes de continuar.")
    return tcpdump_bin


def ensure_nfstream_available() -> None:
    try:
        import nfstream  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("NFStream nao encontrado no ambiente. Instale as dependencias de dataset-tools.") from exc


def build_run_id(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return current.strftime("%Y%m%dT%H%M%SZ")


def build_run_paths(output_dir: Path, run_id: str) -> dict[str, Path]:
    return {
        "pcap_path": output_dir / f"traffic_{run_id}.pcap",
        "flow_csv_path": output_dir / f"flow_features_{run_id}.csv",
        "metadata_path": output_dir / f"metadata_{run_id}.json",
    }


def start_tcpdump(interface: str, filter_expression: str, pcap_path: Path) -> subprocess.Popen[str]:
    tcpdump_bin = ensure_tcpdump_available()
    cmd = [tcpdump_bin, "-i", interface, "-U", "-w", str(pcap_path), filter_expression]
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    time.sleep(1.0)
    if process.poll() is not None:
        stderr = process.stderr.read().strip() if process.stderr else ""
        raise RuntimeError(
            "Falha ao iniciar tcpdump. Rode com sudo ou ajuste permissoes de captura.\n"
            f"Comando: {' '.join(cmd)}\n"
            f"Erro: {stderr}"
        )
    return process


def stop_tcpdump(process: subprocess.Popen[str]) -> str:
    if process.poll() is not None:
        return process.stderr.read().strip() if process.stderr else ""
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=3)
    return process.stderr.read().strip() if process.stderr else ""


def run_benign_generator(
    hub_url: str,
    api_key: str,
    duration_seconds: int,
    seed: int | None,
    request_timeout_seconds: float,
) -> None:
    generator_script = PROJECT_ROOT / "dataset-tools" / "scripts" / "generate_benign_traffic.py"
    cmd = [
        sys.executable,
        str(generator_script),
        "--hub-url",
        hub_url,
        "--api-key",
        api_key,
        "--duration-seconds",
        str(duration_seconds),
        "--request-timeout-seconds",
        str(request_timeout_seconds),
    ]
    if seed is not None:
        cmd.extend(["--seed", str(seed)])
    subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)


def extract_flow_features(pcap_path: Path, csv_path: Path) -> tuple[int, list[str]]:
    from nfstream import NFStreamer

    streamer = NFStreamer(source=str(pcap_path))
    df = streamer.to_pandas()
    df.to_csv(csv_path, index=False)
    return len(df.index), list(df.columns)


def write_metadata(metadata_path: Path, payload: dict[str, Any]) -> None:
    metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def collect_benign_run(
    hub_url: str,
    api_key: str,
    duration_seconds: int,
    interface: str,
    port_range_start: int,
    port_range_end: int,
    output_dir: Path,
    seed: int | None,
    request_timeout_seconds: float,
) -> dict[str, str]:
    ensure_hub_healthy(hub_url)
    ensure_tcpdump_available()
    ensure_nfstream_available()

    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = build_run_id()
    paths = build_run_paths(output_dir, run_id)
    tcpdump_filter = build_tcpdump_filter(port_range_start, port_range_end)
    started_at = datetime.now(timezone.utc)

    process: subprocess.Popen[str] | None = None
    tcpdump_stderr = ""
    try:
        process = start_tcpdump(interface, tcpdump_filter, paths["pcap_path"])
        run_benign_generator(
            hub_url=hub_url,
            api_key=api_key,
            duration_seconds=duration_seconds,
            seed=seed,
            request_timeout_seconds=request_timeout_seconds,
        )
    finally:
        if process is not None:
            tcpdump_stderr = stop_tcpdump(process)

    flow_count, flow_columns = extract_flow_features(paths["pcap_path"], paths["flow_csv_path"])
    finished_at = datetime.now(timezone.utc)

    metadata = {
        "run_id": run_id,
        "scenario": "benign",
        "hub_url": hub_url,
        "duration_seconds": duration_seconds,
        "seed": seed,
        "interface": interface,
        "port_range_start": port_range_start,
        "port_range_end": port_range_end,
        "tcpdump_filter": tcpdump_filter,
        "pcap_path": str(paths["pcap_path"]),
        "flow_csv_path": str(paths["flow_csv_path"]),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "nfstream_flow_count": flow_count,
        "nfstream_columns": flow_columns,
        "tcpdump_stderr": tcpdump_stderr,
    }
    write_metadata(paths["metadata_path"], metadata)

    return {
        "run_id": run_id,
        "pcap_path": str(paths["pcap_path"]),
        "flow_csv_path": str(paths["flow_csv_path"]),
        "metadata_path": str(paths["metadata_path"]),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = collect_benign_run(
            hub_url=args.hub_url,
            api_key=args.api_key,
            duration_seconds=args.duration_seconds,
            interface=args.interface,
            port_range_start=args.port_range_start,
            port_range_end=args.port_range_end,
            output_dir=Path(args.output_dir),
            seed=args.seed,
            request_timeout_seconds=args.request_timeout_seconds,
        )
    except (RuntimeError, httpx.HTTPError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    print("=== Benign Flow Dataset Collection Complete ===")
    print(f"PCAP: {result['pcap_path']}")
    print(f"Flow CSV: {result['flow_csv_path']}")
    print(f"Metadata JSON: {result['metadata_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
