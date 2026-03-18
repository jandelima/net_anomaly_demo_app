#!/usr/bin/env python3
"""Monitor live NFStream flows and write canonical raw and windowed CSV outputs."""

from __future__ import annotations

import argparse
import csv
import json
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


FLOW_COLUMNS = [
    "id",
    "expiration_id",
    "src_ip",
    "src_mac",
    "src_oui",
    "src_port",
    "dst_ip",
    "dst_mac",
    "dst_oui",
    "dst_port",
    "protocol",
    "ip_version",
    "vlan_id",
    "tunnel_id",
    "bidirectional_first_seen_ms",
    "bidirectional_last_seen_ms",
    "bidirectional_duration_ms",
    "bidirectional_packets",
    "bidirectional_bytes",
    "src2dst_first_seen_ms",
    "src2dst_last_seen_ms",
    "src2dst_duration_ms",
    "src2dst_packets",
    "src2dst_bytes",
    "dst2src_first_seen_ms",
    "dst2src_last_seen_ms",
    "dst2src_duration_ms",
    "dst2src_packets",
    "dst2src_bytes",
    "application_name",
    "application_category_name",
    "application_is_guessed",
    "application_confidence",
    "requested_server_name",
    "client_fingerprint",
    "server_fingerprint",
    "user_agent",
    "content_type",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor live NFStream flows into canonical raw and 10-second window CSVs.")
    parser.add_argument("--interface", default="lo")
    parser.add_argument("--output-dir", default="dataset-tools/output/runtime_flow_windows")
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--window-seconds", type=int, default=10)
    parser.add_argument("--port-range-start", type=int, default=8000)
    parser.add_argument("--port-range-end", type=int, default=9000)
    parser.add_argument("--duration-seconds", type=int, default=75)
    parser.add_argument("--idle-timeout-seconds", type=int, default=5)
    parser.add_argument("--active-timeout-seconds", type=int, default=10)
    parser.add_argument("--run-id", default=None)
    return parser.parse_args(argv)


def ensure_nfstream_available() -> None:
    try:
        import nfstream  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("NFStream nao encontrado no ambiente. Instale as dependencias de dataset-tools.") from exc


def build_run_id(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return current.strftime("%Y%m%dT%H%M%SZ")


def compute_window_bounds(last_seen_ms: int, window_seconds: int) -> tuple[int, int]:
    window_size_ms = window_seconds * 1000
    window_start_ms = (int(last_seen_ms) // window_size_ms) * window_size_ms
    return window_start_ms, window_start_ms + window_size_ms


def flow_in_port_range(flow: Any, port_range_start: int, port_range_end: int) -> bool:
    src_port = int(getattr(flow, "src_port", 0) or 0)
    dst_port = int(getattr(flow, "dst_port", 0) or 0)
    return port_range_start <= src_port <= port_range_end or port_range_start <= dst_port <= port_range_end


def flow_to_row(flow: Any) -> dict[str, Any]:
    return {column: getattr(flow, column, "") for column in FLOW_COLUMNS}


def append_row(csv_path: Path, row: dict[str, Any]) -> None:
    file_exists = csv_path.exists()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FLOW_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def build_window_csv_path(windows_dir: Path, window_start_ms: int, window_end_ms: int) -> Path:
    return windows_dir / f"window_{window_start_ms}_{window_end_ms}.csv"


def build_bpf_filter(port_range_start: int, port_range_end: int) -> str:
    if port_range_start <= 0 or port_range_end <= 0 or port_range_start > port_range_end:
        raise ValueError("invalid port range")
    return f"tcp portrange {port_range_start}-{port_range_end}"


def _alarm_handler(signum: int, frame: Any) -> None:
    del signum, frame
    raise TimeoutError


def iter_live_flows(
    interface: str,
    port_range_start: int,
    port_range_end: int,
    idle_timeout_seconds: int,
    active_timeout_seconds: int,
) -> Iterable[Any]:
    from nfstream import NFStreamer

    streamer = NFStreamer(
        source=interface,
        bpf_filter=build_bpf_filter(port_range_start, port_range_end),
        idle_timeout=idle_timeout_seconds,
        active_timeout=active_timeout_seconds,
    )
    for flow in streamer:
        yield flow


def write_metadata(metadata_path: Path, payload: dict[str, Any]) -> None:
    metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def monitor_live_windows(
    interface: str,
    output_dir: Path,
    run_dir: Path | None,
    window_seconds: int,
    port_range_start: int,
    port_range_end: int,
    duration_seconds: int = 75,
    idle_timeout_seconds: int = 5,
    active_timeout_seconds: int = 10,
    run_id: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    if idle_timeout_seconds <= 0 or active_timeout_seconds <= 0:
        raise ValueError("timeouts must be positive")
    if port_range_start <= 0 or port_range_end <= 0 or port_range_start > port_range_end:
        raise ValueError("invalid port range")

    ensure_nfstream_available()
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = run_id or build_run_id()
    run_dir = Path(run_dir) if run_dir else output_dir / run_id
    windows_dir = run_dir / "windows"
    flows_full_path = run_dir / "flows_full.csv"
    metadata_path = run_dir / "metadata.json"
    started_at = datetime.now(timezone.utc).isoformat()

    run_dir.mkdir(parents=True, exist_ok=True)
    with flows_full_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FLOW_COLUMNS)
        writer.writeheader()

    written_windows: set[tuple[int, int]] = set()
    flow_count = 0

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(duration_seconds)
    try:
        for flow in iter_live_flows(
            interface,
            port_range_start,
            port_range_end,
            idle_timeout_seconds,
            active_timeout_seconds,
        ):
            if not flow_in_port_range(flow, port_range_start, port_range_end):
                continue

            row = flow_to_row(flow)
            append_row(flows_full_path, row)

            window_start_ms, window_end_ms = compute_window_bounds(
                getattr(flow, "bidirectional_last_seen_ms"),
                window_seconds,
            )
            append_row(build_window_csv_path(windows_dir, window_start_ms, window_end_ms), row)
            written_windows.add((window_start_ms, window_end_ms))
            flow_count += 1
    except TimeoutError:
        pass
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)

    finished_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "run_id": run_id,
        "interface": interface,
        "window_seconds": window_seconds,
        "port_range_start": port_range_start,
        "port_range_end": port_range_end,
        "duration_seconds": duration_seconds,
        "idle_timeout_seconds": idle_timeout_seconds,
        "active_timeout_seconds": active_timeout_seconds,
        "flow_count": flow_count,
        "window_count": len(written_windows),
        "flows_full_path": str(flows_full_path),
        "windows_dir": str(windows_dir),
        "started_at": started_at,
        "finished_at": finished_at,
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    write_metadata(metadata_path, metadata)

    return {
        "run_id": run_id,
        "flow_count": flow_count,
        "window_count": len(written_windows),
        "output_dir": str(run_dir),
        "flows_full_path": str(flows_full_path),
        "metadata_path": str(metadata_path),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = monitor_live_windows(
            interface=args.interface,
            output_dir=Path(args.output_dir),
            run_dir=Path(args.run_dir) if args.run_dir else None,
            window_seconds=args.window_seconds,
            port_range_start=args.port_range_start,
            port_range_end=args.port_range_end,
            duration_seconds=args.duration_seconds,
            idle_timeout_seconds=args.idle_timeout_seconds,
            active_timeout_seconds=args.active_timeout_seconds,
            run_id=args.run_id,
        )
    except KeyboardInterrupt:
        print("Monitoramento interrompido pelo usuario.")
        return 0
    except (RuntimeError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    print("=== Live Flow Window Monitoring Complete ===")
    print(f"Run ID: {result['run_id']}")
    print(f"Flows gravados: {result['flow_count']}")
    print(f"Janelas gravadas: {result['window_count']}")
    print(f"Flows full CSV: {result['flows_full_path']}")
    print(f"Output: {result['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
