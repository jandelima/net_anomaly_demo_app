#!/usr/bin/env bash

set -euo pipefail

SESSION_NAME="${SESSION_NAME:-smarthome}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_ACTIVATE="${PROJECT_ROOT}/.venv/bin/activate"

if ! command -v tmux >/dev/null 2>&1; then
  echo "Erro: tmux nao encontrado no PATH."
  exit 1
fi

if [[ ! -f "${VENV_ACTIVATE}" ]]; then
  echo "Erro: ambiente virtual nao encontrado em ${VENV_ACTIVATE}"
  exit 1
fi

if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
  echo "Sessao tmux '${SESSION_NAME}' ja existe."
  echo "Use: tmux attach -t ${SESSION_NAME}"
  exit 0
fi

run_in_window() {
  local target="$1"
  local command="$2"
  tmux send-keys -t "${target}" "cd ${PROJECT_ROOT} && source ${VENV_ACTIVATE} && ${command}" C-m
}

tmux new-session -d -s "${SESSION_NAME}" -n hub
run_in_window "${SESSION_NAME}:hub" "uvicorn hub.main:app --host 0.0.0.0 --port 8000"

tmux new-window -t "${SESSION_NAME}" -n light
run_in_window "${SESSION_NAME}:light" "uvicorn devices.light.main:app --host 0.0.0.0 --port 8001"

tmux new-window -t "${SESSION_NAME}" -n lock
run_in_window "${SESSION_NAME}:lock" "uvicorn devices.lock.main:app --host 0.0.0.0 --port 8002"

tmux new-window -t "${SESSION_NAME}" -n thermostat
run_in_window "${SESSION_NAME}:thermostat" "uvicorn devices.thermostat.main:app --host 0.0.0.0 --port 8003"

tmux select-window -t "${SESSION_NAME}:hub"
tmux attach -t "${SESSION_NAME}"
