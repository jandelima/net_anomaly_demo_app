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

    def test_collect_benign_run_writes_metadata_and_invokes_pipeline(self) -> None:
        collect = load_collect_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            fake_process = object()
            fake_flow_columns = ["src_ip", "dst_ip"]

            with patch.object(collect, "ensure_hub_healthy") as ensure_hub_healthy, \
                patch.object(collect, "ensure_tcpdump_available") as ensure_tcpdump_available, \
                patch.object(collect, "ensure_nfstream_available") as ensure_nfstream_available, \
                patch.object(collect, "start_tcpdump", return_value=fake_process) as start_tcpdump, \
                patch.object(collect, "run_benign_generator") as run_benign_generator, \
                patch.object(collect, "stop_tcpdump", return_value="tcpdump done") as stop_tcpdump, \
                patch.object(collect, "extract_flow_features", return_value=(7, fake_flow_columns)) as extract_flow_features:
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
                )

            ensure_hub_healthy.assert_called_once_with("http://localhost:8000")
            ensure_tcpdump_available.assert_called_once_with()
            ensure_nfstream_available.assert_called_once_with()
            start_tcpdump.assert_called_once()
            run_benign_generator.assert_called_once()
            stop_tcpdump.assert_called_once_with(fake_process)
            extract_flow_features.assert_called_once()

            self.assertTrue(result["pcap_path"].endswith(".pcap"))
            self.assertTrue(result["flow_csv_path"].endswith(".csv"))
            self.assertTrue(result["metadata_path"].endswith(".json"))

            metadata_path = Path(result["metadata_path"])
            self.assertTrue(metadata_path.exists())

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["scenario"], "benign")
            self.assertEqual(metadata["hub_url"], "http://localhost:8000")
            self.assertEqual(metadata["duration_seconds"], 300)
            self.assertEqual(metadata["seed"], 42)
            self.assertEqual(metadata["interface"], "lo")
            self.assertEqual(metadata["port_range_start"], 8000)
            self.assertEqual(metadata["port_range_end"], 9000)
            self.assertEqual(metadata["tcpdump_filter"], "tcp portrange 8000-9000")
            self.assertEqual(metadata["nfstream_flow_count"], 7)
            self.assertEqual(metadata["nfstream_columns"], fake_flow_columns)
            self.assertIn("started_at", metadata)
            self.assertIn("finished_at", metadata)


if __name__ == "__main__":
    unittest.main()
