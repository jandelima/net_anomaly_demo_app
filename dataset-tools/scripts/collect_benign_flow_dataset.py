#!/usr/bin/env python3
"""Orchestrate canonical benign flow collection with live monitoring."""

from __future__ import annotations

import argparse
import json
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from math import ceil
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect benign flow data using the canonical live NFStream monitor.")
    parser.add_argument("--hub-url", default="http://localhost:8000")
    parser.add_argument("--api-key", default="devkey")
    parser.add_argument("--duration-seconds", type=int, default=3600)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--request-timeout-seconds", type=float, default=5.0)
    parser.add_argument("--interface", default="lo")
    parser.add_argument("--port-range-start", type=int, default=8000)
    parser.add_argument("--port-range-end", type=int, default=9000)
    parser.add_argument("--window-seconds", type=int, default=10)
    parser.add_argument("--output-dir", default="dataset-tools/output/benign_runs")
    parser.add_argument("--warmup-seconds", type=float, default=1.0)
    parser.add_argument("--drain-seconds", type=float, default=15.0)
    parser.add_argument("--idle-timeout-seconds", type=int, default=5)
    parser.add_argument("--active-timeout-seconds", type=int, default=10)
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


def build_run_id(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return current.strftime("%Y%m%dT%H%M%SZ")


def build_run_paths(output_dir: Path, run_id: str) -> dict[str, Path]:
    run_dir = output_dir / run_id
    return {
        "run_dir": run_dir,
        "pcap_path": run_dir / f"traffic_{run_id}.pcap",
        "flows_full_path": run_dir / "flows_full.csv",
        "windows_dir": run_dir / "windows",
        "metadata_path": run_dir / "metadata.json",
    }


def start_tcpdump(interface: str, filter_expression: str, pcap_path: Path) -> subprocess.Popen[str]:
    tcpdump_bin = ensure_tcpdump_available()
    pcap_path.parent.mkdir(parents=True, exist_ok=True)
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


def build_monitor_command(
    interface: str,
    output_dir: Path,
    run_id: str,
    window_seconds: int,
    port_range_start: int,
    port_range_end: int,
    duration_seconds: int,
    idle_timeout_seconds: int,
    active_timeout_seconds: int,
) -> list[str]:
    monitor_script = PROJECT_ROOT / "dataset-tools" / "scripts" / "monitor_live_flow_windows.py"
    return [
        sys.executable,
        str(monitor_script),
        "--interface",
        interface,
        "--output-dir",
        str(output_dir),
        "--run-id",
        run_id,
        "--window-seconds",
        str(window_seconds),
        "--port-range-start",
        str(port_range_start),
        "--port-range-end",
        str(port_range_end),
        "--duration-seconds",
        str(duration_seconds),
        "--idle-timeout-seconds",
        str(idle_timeout_seconds),
        "--active-timeout-seconds",
        str(active_timeout_seconds),
    ]


def start_live_monitor(
    interface: str,
    output_dir: Path,
    run_id: str,
    window_seconds: int,
    port_range_start: int,
    port_range_end: int,
    duration_seconds: int,
    idle_timeout_seconds: int,
    active_timeout_seconds: int,
) -> subprocess.Popen[str]:
    command = build_monitor_command(
        interface=interface,
        output_dir=output_dir,
        run_id=run_id,
        window_seconds=window_seconds,
        port_range_start=port_range_start,
        port_range_end=port_range_end,
        duration_seconds=duration_seconds,
        idle_timeout_seconds=idle_timeout_seconds,
        active_timeout_seconds=active_timeout_seconds,
    )
    return subprocess.Popen(command, cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def wait_for_process(process: subprocess.Popen[str], timeout_seconds: float, name: str) -> tuple[str, str]:
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.terminate()
        stdout, stderr = process.communicate(timeout=5)
        raise RuntimeError(f"{name} excedeu o tempo esperado de execucao.")
    if process.returncode != 0:
        raise RuntimeError(
            f"{name} falhou.\nstdout: {stdout}\nstderr: {stderr}"
        )
    return stdout, stderr


def stream_progress(
    process: subprocess.Popen[str],
    label: str,
    heartbeat_seconds: float = 30.0,
) -> None:
    started = time.monotonic()
    next_heartbeat = heartbeat_seconds
    while process.poll() is None:
        elapsed = time.monotonic() - started
        if elapsed >= next_heartbeat:
            print(f"[progresso] {label} ainda em execução... {int(elapsed)}s decorridos")
            next_heartbeat += heartbeat_seconds
        time.sleep(1.0)


def run_benign_generator(
    hub_url: str,
    api_key: str,
    duration_seconds: int,
    seed: int | None,
    request_timeout_seconds: float,
) -> tuple[str, str]:
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
    process = subprocess.Popen(cmd, cwd=PROJECT_ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stream_progress(process, "Gerador benigno")
    stdout, stderr = wait_for_process(process, timeout_seconds=max(5.0, duration_seconds + 10.0), name="gerador benigno")
    if process.returncode != 0:
        raise RuntimeError(
            "Gerador benigno falhou.\n"
            f"Comando: {' '.join(cmd)}\n"
            f"stdout: {stdout}\n"
            f"stderr: {stderr}"
        )
    print(stdout, end="")
    return stdout, stderr


def write_metadata(metadata_path: Path, payload: dict[str, Any]) -> None:
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
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
    warmup_seconds: float,
    drain_seconds: float,
    idle_timeout_seconds: int,
    active_timeout_seconds: int,
    window_seconds: int = 10,
) -> dict[str, str]:
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    if request_timeout_seconds <= 0:
        raise ValueError("request_timeout_seconds must be positive")
    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")
    if warmup_seconds < 0 or drain_seconds < 0:
        raise ValueError("warmup_seconds and drain_seconds must be non-negative")
    if idle_timeout_seconds <= 0 or active_timeout_seconds <= 0:
        raise ValueError("timeouts must be positive")

    ensure_hub_healthy(hub_url)
    ensure_tcpdump_available()

    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = build_run_id()
    paths = build_run_paths(output_dir, run_id)
    paths["run_dir"].mkdir(parents=True, exist_ok=True)
    tcpdump_filter = build_tcpdump_filter(port_range_start, port_range_end)
    started_at = datetime.now(timezone.utc)
    total_monitor_duration = max(1, int(ceil(warmup_seconds + duration_seconds + drain_seconds)))

    tcpdump_process: subprocess.Popen[str] | None = None
    monitor_process: subprocess.Popen[str] | None = None
    tcpdump_stderr = ""
    monitor_stdout = ""
    monitor_stderr = ""
    generator_stdout = ""
    generator_stderr = ""

    try:
        print("[1/5] Iniciando tcpdump...")
        tcpdump_process = start_tcpdump(interface, tcpdump_filter, paths["pcap_path"])
        print("[2/5] Iniciando monitor live canônico...")
        monitor_process = start_live_monitor(
            interface=interface,
            output_dir=output_dir,
            run_id=run_id,
            window_seconds=window_seconds,
            port_range_start=port_range_start,
            port_range_end=port_range_end,
            duration_seconds=total_monitor_duration,
            idle_timeout_seconds=idle_timeout_seconds,
            active_timeout_seconds=active_timeout_seconds,
        )
        if warmup_seconds > 0:
            print(f"[3/5] Warmup de {warmup_seconds:.1f}s antes do gerador benigno...")
            time.sleep(warmup_seconds)
        print(f"[4/5] Rodando gerador benigno por {duration_seconds}s...")
        generator_stdout, generator_stderr = run_benign_generator(
            hub_url=hub_url,
            api_key=api_key,
            duration_seconds=duration_seconds,
            seed=seed,
            request_timeout_seconds=request_timeout_seconds,
        )
    finally:
        if tcpdump_process is not None:
            tcpdump_stderr = stop_tcpdump(tcpdump_process)

    if monitor_process is None:
        raise RuntimeError("Monitor live nao foi iniciado.")

    print("[5/5] Aguardando finalização do monitor live...")
    stream_progress(monitor_process, "Monitor live")
    monitor_stdout, monitor_stderr = wait_for_process(
        monitor_process,
        timeout_seconds=max(5.0, total_monitor_duration + 5.0),
        name="monitor live",
    )
    finished_at = datetime.now(timezone.utc)

    metadata: dict[str, Any] = {}
    if paths["metadata_path"].exists():
        metadata = json.loads(paths["metadata_path"].read_text(encoding="utf-8"))

    metadata.update(
        {
            "run_id": run_id,
            "scenario": "benign",
            "hub_url": hub_url,
            "duration_seconds": duration_seconds,
            "seed": seed,
            "interface": interface,
            "port_range_start": port_range_start,
            "port_range_end": port_range_end,
            "window_seconds": window_seconds,
            "warmup_seconds": warmup_seconds,
            "drain_seconds": drain_seconds,
            "idle_timeout_seconds": idle_timeout_seconds,
            "active_timeout_seconds": active_timeout_seconds,
            "request_timeout_seconds": request_timeout_seconds,
            "tcpdump_filter": tcpdump_filter,
            "pcap_path": str(paths["pcap_path"]),
            "flows_full_path": str(paths["flows_full_path"]),
            "windows_dir": str(paths["windows_dir"]),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "monitor_stdout": monitor_stdout,
            "monitor_stderr": monitor_stderr,
            "generator_stdout": generator_stdout,
            "generator_stderr": generator_stderr,
            "tcpdump_stderr": tcpdump_stderr,
        }
    )
    write_metadata(paths["metadata_path"], metadata)

    return {
        "run_id": run_id,
        "pcap_path": str(paths["pcap_path"]),
        "flows_full_path": str(paths["flows_full_path"]),
        "windows_dir": str(paths["windows_dir"]),
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
            warmup_seconds=args.warmup_seconds,
            drain_seconds=args.drain_seconds,
            idle_timeout_seconds=args.idle_timeout_seconds,
            active_timeout_seconds=args.active_timeout_seconds,
            window_seconds=args.window_seconds,
        )
    except (RuntimeError, httpx.HTTPError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    print("=== Benign Flow Dataset Collection Complete ===")
    print(f"PCAP: {result['pcap_path']}")
    print(f"Flows Full CSV: {result['flows_full_path']}")
    print(f"Windows Dir: {result['windows_dir']}")
    print(f"Metadata JSON: {result['metadata_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
