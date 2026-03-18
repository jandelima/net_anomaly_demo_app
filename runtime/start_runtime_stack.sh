#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${1:-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_DIR="$PROJECT_ROOT/runtime/runs/$RUN_ID"
FLOW_DIR="$RUN_DIR/flows"
APP_DIR="$RUN_DIR/app"
LOG_DIR="$RUN_DIR/logs"
PID_DIR="$RUN_DIR/pids"

mkdir -p "$FLOW_DIR/windows" "$APP_DIR/windows" "$LOG_DIR" "$PID_DIR"

sudo -v

sudo "$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/dataset-tools/scripts/monitor_live_flow_windows.py" \
  --interface lo \
  --output-dir "$PROJECT_ROOT/runtime/runs" \
  --run-id "$RUN_ID" \
  --run-dir "$FLOW_DIR" \
  --window-seconds 10 \
  --port-range-start 8000 \
  --port-range-end 9000 \
  --duration-seconds 14400 \
  --idle-timeout-seconds 5 \
  --active-timeout-seconds 10 \
  > "$LOG_DIR/flow_monitor.log" 2>&1 &
echo $! > "$PID_DIR/flow_monitor.pid"

"$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/dataset-tools/scripts/monitor_live_app_windows.py" \
  --input-csv "$PROJECT_ROOT/data/app_level/hub_requests.csv" \
  --output-dir "$PROJECT_ROOT/runtime/runs" \
  --run-id "$RUN_ID" \
  --run-dir "$APP_DIR" \
  --window-seconds 10 \
  --poll-interval 2 \
  > "$LOG_DIR/app_monitor.log" 2>&1 &
echo $! > "$PID_DIR/app_monitor.pid"

python3 "$PROJECT_ROOT/runtime/scripts/live_flows_inference.py" \
  --windows-dir "$FLOW_DIR/windows" \
  --flows-model-dir "$PROJECT_ROOT/runtime/models/flows_model" \
  --poll-interval 2 \
  --grace-period 10 \
  --output-csv "$FLOW_DIR/inference_results.csv" \
  > "$LOG_DIR/flow_infer.log" 2>&1 &
echo $! > "$PID_DIR/flow_infer.pid"

python3 "$PROJECT_ROOT/runtime/scripts/infer_live_app_windows.py" \
  --windows-dir "$APP_DIR/windows" \
  --hub-model-dir "$PROJECT_ROOT/runtime/models/hub_model" \
  --poll-interval 2 \
  --grace-period 10 \
  --output-csv "$APP_DIR/inference_results.csv" \
  > "$LOG_DIR/app_infer.log" 2>&1 &
echo $! > "$PID_DIR/app_infer.pid"

cat <<INFO
Runtime stack started.
Run ID: $RUN_ID
Run dir: $RUN_DIR

Useful paths:
- Flow windows: $FLOW_DIR/windows
- Flow results: $FLOW_DIR/inference_results.csv
- App windows: $APP_DIR/windows
- App results: $APP_DIR/inference_results.csv
- Logs: $LOG_DIR

Tail examples:
- tail -f "$FLOW_DIR/inference_results.csv"
- tail -f "$APP_DIR/inference_results.csv"
- tail -f "$LOG_DIR/flow_monitor.log"
INFO
