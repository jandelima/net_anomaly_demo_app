#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

from inference_api import is_anomaly_flows, load_flows_model


def main() -> int:
    windows_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "/home/janfilho/net_anomaly_demo_app/dataset-tools/output/benign_runs/20260315T043430Z/windows"
    )
    if not windows_dir.is_dir():
        print(f"Directory not found: {windows_dir}", file=sys.stderr)
        return 1

    files = sorted(windows_dir.glob("window_*.csv"))
    if not files:
        print(f"No window CSV files found in: {windows_dir}", file=sys.stderr)
        return 1

    model, scaler, threshold = load_flows_model("flows_model")

    zeros = 0
    ones = 0
    for csv_file in files:
        pred = is_anomaly_flows(model, scaler, threshold, str(csv_file))
        if pred == 0:
            zeros += 1
        else:
            ones += 1
        print(f"{csv_file.name} -> {pred}")

    total = zeros + ones
    zero_pct = (zeros / total) * 100 if total else 0.0
    one_pct = (ones / total) * 100 if total else 0.0

    print("")
    print(f"Total windows: {total}")
    print(f"0s: {zeros} ({zero_pct:.2f}%)")
    print(f"1s: {ones} ({one_pct:.2f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
