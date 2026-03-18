# Runtime Monitoring

This directory contains the consolidated live runtime workflow for flow-level and app-level monitoring.

## Layout

Each live run is written to:

`runtime/runs/<run_id>/`

With this structure:

- `flows/windows/`
- `flows/flows_full.csv`
- `flows/inference_results.csv`
- `flows/metadata.json`
- `app/windows/`
- `app/inference_results.csv`
- `app/metadata.json`
- `logs/`
- `pids/`

## Start everything

```bash
cd /home/janfilho/net_anomaly_demo_app
./runtime/start_runtime_stack.sh
```

Optional custom run id:

```bash
./runtime/start_runtime_stack.sh my-runtime-run
```

## Stop everything

```bash
cd /home/janfilho/net_anomaly_demo_app
./runtime/stop_runtime_stack.sh <run_id>
```

## Notes

- Flow monitoring still uses `dataset-tools/scripts/monitor_live_flow_windows.py`.
- App monitoring still uses `dataset-tools/scripts/monitor_live_app_windows.py`.
- Runtime inference and model assets now live under `runtime/` in this repository.
- `python3` is used for inference because this Raspberry is using the system Torch installation.
