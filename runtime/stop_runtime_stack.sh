#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ $# -lt 1 ]]; then
  echo "usage: $0 <run_id>" >&2
  exit 1
fi

RUN_ID="$1"
RUN_DIR="$PROJECT_ROOT/runtime/runs/$RUN_ID"
PID_DIR="$RUN_DIR/pids"

if [[ ! -d "$PID_DIR" ]]; then
  echo "pid directory not found: $PID_DIR" >&2
  exit 1
fi

kill_if_present() {
  local pid_file="$1"
  local use_sudo="$2"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file")"
    if [[ -n "$pid" ]]; then
      if [[ "$use_sudo" == "yes" ]]; then
        sudo kill "$pid" 2>/dev/null || true
      else
        kill "$pid" 2>/dev/null || true
      fi
    fi
  fi
}

kill_if_present "$PID_DIR/flow_monitor.pid" yes
kill_if_present "$PID_DIR/app_monitor.pid" no
kill_if_present "$PID_DIR/flow_infer.pid" no
kill_if_present "$PID_DIR/app_infer.pid" no

echo "Stopped runtime stack for run_id=$RUN_ID"
