import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "dataset-tools" / "scripts" / "collect_benign_flow_dataset.py"


def load_collect_module():
    spec = importlib.util.spec_from_file_location("collect_benign_flow_dataset", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CollectBenignFlowDatasetTests(unittest.TestCase):
    def test_build_tcpdump_filter_uses_port_range(self) -> None:
        collect = load_collect_module()

        self.assertEqual(collect.build_tcpdump_filter(8000, 9000), "tcp portrange 8000-9000")

    def test_parse_args_uses_expected_defaults(self) -> None:
        collect = load_collect_module()

        args = collect.parse_args([])

        self.assertEqual(args.hub_url, "http://localhost:8000")
        self.assertEqual(args.api_key, "devkey")
        self.assertEqual(args.duration_seconds, 3600)
        self.assertEqual(args.interface, "lo")
        self.assertEqual(args.port_range_start, 8000)
        self.assertEqual(args.port_range_end, 9000)
        self.assertEqual(args.output_dir, "dataset-tools/output/benign_runs")
        self.assertIsNone(args.seed)
        self.assertEqual(args.warmup_seconds, 1.0)
        self.assertEqual(args.drain_seconds, 15.0)
        self.assertEqual(args.idle_timeout_seconds, 5)
        self.assertEqual(args.active_timeout_seconds, 10)

    def test_collect_benign_run_writes_metadata_and_invokes_pipeline(self) -> None:
        collect = load_collect_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            fake_tcpdump_process = object()
            fake_monitor_process = object()

            with patch.object(collect, "ensure_hub_healthy") as ensure_hub_healthy, \
                patch.object(collect, "ensure_tcpdump_available") as ensure_tcpdump_available, \
                patch.object(collect, "build_run_id", return_value="test-run"), \
                patch.object(collect, "start_tcpdump", return_value=fake_tcpdump_process) as start_tcpdump, \
                patch.object(collect, "start_live_monitor", return_value=fake_monitor_process) as start_live_monitor, \
                patch.object(collect, "run_benign_generator", return_value=("generator done", "")) as run_benign_generator, \
                patch.object(collect, "stop_tcpdump", return_value="tcpdump done") as stop_tcpdump, \
                patch.object(collect, "wait_for_process", return_value=("monitor done", "")) as wait_for_process:
                result = collect.collect_benign_run(
                    hub_url="http://localhost:8000",
                    api_key="devkey",
                    duration_seconds=300,
                    interface="lo",
                    port_range_start=8000,
                    port_range_end=9000,
                    output_dir=output_dir,
                    seed=42,
                    request_timeout_seconds=5.0,
                    warmup_seconds=1.0,
                    drain_seconds=15.0,
                    idle_timeout_seconds=5,
                    active_timeout_seconds=10,
                )

            ensure_hub_healthy.assert_called_once_with("http://localhost:8000")
            ensure_tcpdump_available.assert_called_once_with()
            start_tcpdump.assert_called_once()
            start_live_monitor.assert_called_once()
            run_benign_generator.assert_called_once()
            stop_tcpdump.assert_called_once_with(fake_tcpdump_process)
            wait_for_process.assert_called_once()

            self.assertTrue(result["pcap_path"].endswith(".pcap"))
            self.assertTrue(result["flows_full_path"].endswith("flows_full.csv"))
            self.assertTrue(result["windows_dir"].endswith("windows"))
            self.assertTrue(result["metadata_path"].endswith(".json"))

            metadata_path = Path(result["metadata_path"])
            self.assertTrue(metadata_path.exists())

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["run_id"], "test-run")
            self.assertEqual(metadata["scenario"], "benign")
            self.assertEqual(metadata["hub_url"], "http://localhost:8000")
            self.assertEqual(metadata["duration_seconds"], 300)
            self.assertEqual(metadata["seed"], 42)
            self.assertEqual(metadata["interface"], "lo")
            self.assertEqual(metadata["port_range_start"], 8000)
            self.assertEqual(metadata["port_range_end"], 9000)
            self.assertEqual(metadata["tcpdump_filter"], "tcp portrange 8000-9000")
            self.assertEqual(metadata["warmup_seconds"], 1.0)
            self.assertEqual(metadata["drain_seconds"], 15.0)
            self.assertEqual(metadata["idle_timeout_seconds"], 5)
            self.assertEqual(metadata["active_timeout_seconds"], 10)
            self.assertEqual(metadata["pcap_path"], str(output_dir / "test-run" / "traffic_test-run.pcap"))
            self.assertEqual(metadata["flows_full_path"], str(output_dir / "test-run" / "flows_full.csv"))
            self.assertEqual(metadata["windows_dir"], str(output_dir / "test-run" / "windows"))
            self.assertEqual(metadata["monitor_stdout"], "monitor done")
            self.assertEqual(metadata["monitor_stderr"], "")
            self.assertEqual(metadata["generator_stdout"], "generator done")
            self.assertEqual(metadata["generator_stderr"], "")
            self.assertIn("started_at", metadata)
            self.assertIn("finished_at", metadata)


if __name__ == "__main__":
    unittest.main()
