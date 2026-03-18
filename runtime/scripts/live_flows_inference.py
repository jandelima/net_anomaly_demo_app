#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from inference_api import is_anomaly_flows, load_flows_model


WINDOW_RE = re.compile(r"^window_(\d+)_(\d+)\.csv$")
OUTPUT_FIELDS = ("window_file", "prediction", "processed_at")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Continuously infer anomalies from live flow window CSVs.")
    parser.add_argument("--windows-dir", required=True)
    parser.add_argument("--flows-model-dir", required=True)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--grace-period", type=float, default=10.0)
    parser.add_argument("--output-csv", required=True)
    return parser.parse_args(argv)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_window_file(path: Path) -> tuple[int, int] | None:
    match = WINDOW_RE.match(path.name)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def load_processed_files(output_csv: Path) -> set[str]:
    if not output_csv.exists():
        return set()

    processed: set[str] = set()
    with output_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            window_file = row.get("window_file")
            if window_file:
                processed.add(window_file)
    return processed


def append_result(output_csv: Path, window_file: str, prediction: int) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    file_exists = output_csv.exists()
    with output_csv.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(
            {
                "window_file": window_file,
                "prediction": prediction,
                "processed_at": utc_now_iso(),
            }
        )


def iter_window_files(windows_dir: Path) -> list[tuple[int, int, Path]]:
    windows: list[tuple[int, int, Path]] = []
    for path in windows_dir.glob("window_*.csv"):
        bounds = parse_window_file(path)
        if bounds is None:
            continue
        start_ms, end_ms = bounds
        windows.append((start_ms, end_ms, path))
    windows.sort(key=lambda item: (item[0], item[1], item[2].name))
    return windows


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    windows_dir = Path(args.windows_dir)
    flows_model_dir = Path(args.flows_model_dir)
    output_csv = Path(args.output_csv)
    grace_period_ms = int(args.grace_period * 1000)

    if not windows_dir.is_dir():
        print(f"windows directory not found: {windows_dir}", file=sys.stderr)
        return 1
    if not flows_model_dir.is_dir():
        print(f"flows model directory not found: {flows_model_dir}", file=sys.stderr)
        return 1

    model, scaler, threshold = load_flows_model(str(flows_model_dir))
    processed_files = load_processed_files(output_csv)

    while True:
        now_ms = int(time.time() * 1000)
        for start_ms, end_ms, path in iter_window_files(windows_dir):
            del start_ms
            if path.name in processed_files:
                continue
            if now_ms < end_ms + grace_period_ms:
                continue

            try:
                prediction = is_anomaly_flows(model, scaler, threshold, str(path))
                append_result(output_csv, path.name, int(prediction))
                processed_files.add(path.name)
            except Exception as exc:
                print(f"[error] failed to process {path.name}: {exc}", file=sys.stderr, flush=True)

        time.sleep(args.poll_interval)


if __name__ == "__main__":
    raise SystemExit(main())
