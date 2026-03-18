#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Continuously split hub app-level CSV rows into fixed window CSVs.")
    parser.add_argument("--input-csv", default="data/app_level/hub_requests.csv")
    parser.add_argument("--output-dir", default="dataset-tools/output/runtime_app_windows")
    parser.add_argument("--window-seconds", type=int, default=10)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    return parser.parse_args(argv)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_run_id(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return current.strftime("%Y%m%dT%H%M%SZ")


def compute_window_bounds(timestamp_ms: int, window_seconds: int) -> tuple[int, int]:
    window_size_ms = window_seconds * 1000
    window_start_ms = (int(timestamp_ms) // window_size_ms) * window_size_ms
    return window_start_ms, window_start_ms + window_size_ms


def build_window_csv_path(windows_dir: Path, window_start_ms: int, window_end_ms: int) -> Path:
    return windows_dir / f"window_{window_start_ms}_{window_end_ms}.csv"


def append_row(csv_path: Path, fieldnames: list[str], row: dict[str, Any]) -> None:
    file_exists = csv_path.exists()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({name: row.get(name, "") for name in fieldnames})


def write_metadata(metadata_path: Path, payload: dict[str, Any]) -> None:
    metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@dataclass
class TailState:
    offset: int = 0
    partial: str = ""
    fieldnames: list[str] = field(default_factory=list)


def read_new_rows(input_csv: Path, state: TailState) -> list[dict[str, str]]:
    if not input_csv.exists():
        return []

    file_size = input_csv.stat().st_size
    if file_size < state.offset:
        state.offset = 0
        state.partial = ""
        state.fieldnames = []

    with input_csv.open("r", encoding="utf-8", newline="") as handle:
        handle.seek(state.offset)
        chunk = handle.read()
        state.offset = handle.tell()

    if not chunk:
        return []

    text = state.partial + chunk
    if text.endswith("\n"):
        lines = text.splitlines()
        state.partial = ""
    else:
        lines = text.splitlines()
        state.partial = lines.pop() if lines else text

    if not lines:
        return []

    if not state.fieldnames:
        header_line = lines.pop(0)
        state.fieldnames = next(csv.reader([header_line]))

    if not lines:
        return []

    reader = csv.DictReader(io.StringIO("\n".join(lines)), fieldnames=state.fieldnames)
    return [row for row in reader]


def monitor_live_app_windows(
    input_csv: Path,
    output_dir: Path,
    window_seconds: int,
    poll_interval: float,
) -> int:
    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")
    if poll_interval <= 0:
        raise ValueError("poll_interval must be positive")

    run_id = build_run_id()
    run_dir = output_dir / run_id
    windows_dir = run_dir / "windows"
    metadata_path = run_dir / "metadata.json"
    run_dir.mkdir(parents=True, exist_ok=True)

    state = TailState()
    written_windows: set[tuple[int, int]] = set()
    row_count = 0
    metadata = {
        "run_id": run_id,
        "input_csv": str(input_csv),
        "window_seconds": window_seconds,
        "output_dir": str(run_dir),
        "windows_dir": str(windows_dir),
        "started_at": utc_now_iso(),
        "last_updated_at": utc_now_iso(),
        "row_count": 0,
        "window_count": 0,
    }
    write_metadata(metadata_path, metadata)

    while True:
        try:
            rows = read_new_rows(input_csv, state)
            for row in rows:
                timestamp_ms = int(row["timestamp_ms"])
                window_start_ms, window_end_ms = compute_window_bounds(timestamp_ms, window_seconds)
                append_row(
                    build_window_csv_path(windows_dir, window_start_ms, window_end_ms),
                    state.fieldnames,
                    row,
                )
                written_windows.add((window_start_ms, window_end_ms))
                row_count += 1
            if rows:
                metadata["last_updated_at"] = utc_now_iso()
                metadata["row_count"] = row_count
                metadata["window_count"] = len(written_windows)
                write_metadata(metadata_path, metadata)
        except Exception as exc:
            print(f"[error] app monitor failed: {exc}", file=sys.stderr, flush=True)

        time.sleep(poll_interval)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return monitor_live_app_windows(
            input_csv=Path(args.input_csv),
            output_dir=Path(args.output_dir),
            window_seconds=args.window_seconds,
            poll_interval=args.poll_interval,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
