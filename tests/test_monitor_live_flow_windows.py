import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "dataset-tools" / "scripts" / "monitor_live_flow_windows.py"


def load_monitor_module():
    spec = importlib.util.spec_from_file_location("monitor_live_flow_windows", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeFlow:
    def __init__(self, **values):
        for key, value in values.items():
            setattr(self, key, value)


class MonitorLiveFlowWindowsTests(unittest.TestCase):
    def test_parse_args_uses_expected_defaults(self) -> None:
        monitor = load_monitor_module()

        args = monitor.parse_args([])

        self.assertEqual(args.interface, "lo")
        self.assertEqual(args.output_dir, "dataset-tools/output/runtime_flow_windows")
        self.assertEqual(args.window_seconds, 10)
        self.assertEqual(args.port_range_start, 8000)
        self.assertEqual(args.port_range_end, 9000)
        self.assertEqual(args.duration_seconds, 75)
        self.assertEqual(args.idle_timeout_seconds, 5)
        self.assertEqual(args.active_timeout_seconds, 10)
        self.assertIsNone(args.run_id)

    def test_iter_live_flows_builds_nfstream_with_timeouts_and_filter(self) -> None:
        monitor = load_monitor_module()
        captured_kwargs = {}

        class FakeStreamer:
            def __init__(self, **kwargs):
                captured_kwargs.update(kwargs)

            def __iter__(self):
                return iter(())

        with patch.dict(sys.modules, {"nfstream": type("nfstream", (), {"NFStreamer": FakeStreamer})}):
            list(
                monitor.iter_live_flows(
                    interface="lo",
                    port_range_start=8000,
                    port_range_end=9000,
                    idle_timeout_seconds=5,
                    active_timeout_seconds=10,
                )
            )

        self.assertEqual(captured_kwargs["source"], "lo")
        self.assertEqual(captured_kwargs["bpf_filter"], "tcp portrange 8000-9000")
        self.assertEqual(captured_kwargs["idle_timeout"], 5)
        self.assertEqual(captured_kwargs["active_timeout"], 10)

    def test_compute_window_bounds_uses_last_seen_epoch_bucket(self) -> None:
        monitor = load_monitor_module()

        start_ms, end_ms = monitor.compute_window_bounds(1773454846086, window_seconds=10)

        self.assertEqual(start_ms, 1773454840000)
        self.assertEqual(end_ms, 1773454850000)

    def test_monitor_live_windows_writes_flows_full_windows_and_metadata(self) -> None:
        monitor = load_monitor_module()

        flows = [
            _FakeFlow(
                id=1,
                expiration_id=0,
                src_ip="127.0.0.1",
                src_mac="00:00:00:00:00:00",
                src_oui="00:00:00",
                src_port=38144,
                dst_ip="127.0.0.1",
                dst_mac="00:00:00:00:00:00",
                dst_oui="00:00:00",
                dst_port=8000,
                protocol=6,
                ip_version=4,
                vlan_id=0,
                tunnel_id=0,
                bidirectional_first_seen_ms=1773463605029,
                bidirectional_last_seen_ms=1773463605032,
                bidirectional_duration_ms=3,
                bidirectional_packets=12,
                bidirectional_bytes=1262,
                src2dst_first_seen_ms=1773463605029,
                src2dst_last_seen_ms=1773463605032,
                src2dst_duration_ms=3,
                src2dst_packets=7,
                src2dst_bytes=618,
                dst2src_first_seen_ms=1773463605029,
                dst2src_last_seen_ms=1773463605032,
                dst2src_duration_ms=3,
                dst2src_packets=5,
                dst2src_bytes=644,
                application_name="HTTP",
                application_category_name="Web",
                application_is_guessed=0,
                application_confidence=6,
                requested_server_name="localhost",
                client_fingerprint="",
                server_fingerprint="",
                user_agent="python-httpx/0.28.1",
                content_type="application/json",
            ),
            _FakeFlow(
                id=2,
                expiration_id=0,
                src_ip="127.0.0.1",
                src_mac="00:00:00:00:00:00",
                src_oui="00:00:00",
                src_port=39244,
                dst_ip="127.0.0.1",
                dst_mac="00:00:00:00:00:00",
                dst_oui="00:00:00",
                dst_port=8000,
                protocol=6,
                ip_version=4,
                vlan_id=0,
                tunnel_id=0,
                bidirectional_first_seen_ms=1773463654728,
                bidirectional_last_seen_ms=1773463654740,
                bidirectional_duration_ms=12,
                bidirectional_packets=14,
                bidirectional_bytes=1634,
                src2dst_first_seen_ms=1773463654728,
                src2dst_last_seen_ms=1773463654740,
                src2dst_duration_ms=12,
                src2dst_packets=8,
                src2dst_bytes=835,
                dst2src_first_seen_ms=1773463654728,
                dst2src_last_seen_ms=1773463654740,
                dst2src_duration_ms=12,
                dst2src_packets=6,
                dst2src_bytes=799,
                application_name="HTTP",
                application_category_name="Web",
                application_is_guessed=0,
                application_confidence=6,
                requested_server_name="localhost",
                client_fingerprint="",
                server_fingerprint="",
                user_agent="python-httpx/0.28.1",
                content_type="application/json",
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            with patch.object(monitor, "iter_live_flows", return_value=iter(flows)), \
                patch.object(monitor, "build_run_id", return_value="test-run"):
                result = monitor.monitor_live_windows(
                    interface="lo",
                    output_dir=output_dir,
                    window_seconds=10,
                    port_range_start=8000,
                    port_range_end=9000,
                )

            self.assertEqual(result["flow_count"], 2)
            self.assertEqual(result["window_count"], 2)
            self.assertEqual(result["run_id"], "test-run")

            run_dir = output_dir / "test-run"
            flows_full = run_dir / "flows_full.csv"
            windows_dir = run_dir / "windows"
            metadata_path = run_dir / "metadata.json"
            first_window = windows_dir / "window_1773463600000_1773463610000.csv"
            second_window = windows_dir / "window_1773463650000_1773463660000.csv"

            self.assertTrue(flows_full.exists())
            self.assertTrue(first_window.exists())
            self.assertTrue(second_window.exists())
            self.assertTrue(metadata_path.exists())

            self.assertEqual(flows_full.read_text(encoding="utf-8").count("\n"), 3)
            self.assertEqual(first_window.read_text(encoding="utf-8").count("\n"), 2)
            self.assertEqual(second_window.read_text(encoding="utf-8").count("\n"), 2)

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["run_id"], "test-run")
            self.assertEqual(metadata["flow_count"], 2)
            self.assertEqual(metadata["window_count"], 2)
            self.assertEqual(metadata["flows_full_path"], str(flows_full))

    def test_monitor_live_windows_ignores_flows_outside_port_range(self) -> None:
        monitor = load_monitor_module()

        flows = [
            _FakeFlow(
                id=3,
                expiration_id=0,
                src_ip="127.0.0.1",
                src_mac="00:00:00:00:00:00",
                src_oui="00:00:00",
                src_port=50000,
                dst_ip="127.0.0.1",
                dst_mac="00:00:00:00:00:00",
                dst_oui="00:00:00",
                dst_port=7000,
                protocol=6,
                ip_version=4,
                vlan_id=0,
                tunnel_id=0,
                bidirectional_first_seen_ms=1773463600000,
                bidirectional_last_seen_ms=1773463600100,
                bidirectional_duration_ms=100,
                bidirectional_packets=2,
                bidirectional_bytes=120,
                src2dst_first_seen_ms=1773463600000,
                src2dst_last_seen_ms=1773463600100,
                src2dst_duration_ms=100,
                src2dst_packets=1,
                src2dst_bytes=66,
                dst2src_first_seen_ms=1773463600000,
                dst2src_last_seen_ms=1773463600100,
                dst2src_duration_ms=100,
                dst2src_packets=1,
                dst2src_bytes=54,
                application_name="Unknown",
                application_category_name="Unspecified",
                application_is_guessed=0,
                application_confidence=0,
                requested_server_name="",
                client_fingerprint="",
                server_fingerprint="",
                user_agent="",
                content_type="",
            )
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            with patch.object(monitor, "iter_live_flows", return_value=iter(flows)), \
                patch.object(monitor, "build_run_id", return_value="test-run"):
                result = monitor.monitor_live_windows(
                    interface="lo",
                    output_dir=output_dir,
                    window_seconds=10,
                    port_range_start=8000,
                    port_range_end=9000,
                )

            self.assertEqual(result["flow_count"], 0)
            self.assertEqual(result["window_count"], 0)
            run_dir = output_dir / "test-run"
            self.assertTrue((run_dir / "flows_full.csv").exists())
            self.assertTrue((run_dir / "metadata.json").exists())
            self.assertFalse((run_dir / "windows").exists())

    def test_monitor_live_windows_uses_explicit_run_id(self) -> None:
        monitor = load_monitor_module()

        flows = [
            _FakeFlow(
                id=10,
                expiration_id=0,
                src_ip="127.0.0.1",
                src_mac="00:00:00:00:00:00",
                src_oui="00:00:00",
                src_port=38144,
                dst_ip="127.0.0.1",
                dst_mac="00:00:00:00:00:00",
                dst_oui="00:00:00",
                dst_port=8000,
                protocol=6,
                ip_version=4,
                vlan_id=0,
                tunnel_id=0,
                bidirectional_first_seen_ms=1773463605029,
                bidirectional_last_seen_ms=1773463605032,
                bidirectional_duration_ms=3,
                bidirectional_packets=12,
                bidirectional_bytes=1262,
                src2dst_first_seen_ms=1773463605029,
                src2dst_last_seen_ms=1773463605032,
                src2dst_duration_ms=3,
                src2dst_packets=7,
                src2dst_bytes=618,
                dst2src_first_seen_ms=1773463605029,
                dst2src_last_seen_ms=1773463605032,
                dst2src_duration_ms=3,
                dst2src_packets=5,
                dst2src_bytes=644,
                application_name="HTTP",
                application_category_name="Web",
                application_is_guessed=0,
                application_confidence=6,
                requested_server_name="localhost",
                client_fingerprint="",
                server_fingerprint="",
                user_agent="python-httpx/0.28.1",
                content_type="application/json",
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            with patch.object(monitor, "iter_live_flows", return_value=iter(flows)):
                result = monitor.monitor_live_windows(
                    interface="lo",
                    output_dir=output_dir,
                    window_seconds=10,
                    port_range_start=8000,
                    port_range_end=9000,
                    idle_timeout_seconds=5,
                    active_timeout_seconds=10,
                    run_id="fixed-run",
                )

            self.assertEqual(result["flow_count"], 1)
            self.assertEqual(result["run_id"], "fixed-run")

            run_dir = output_dir / "fixed-run"
            self.assertTrue((run_dir / "flows_full.csv").exists())
            self.assertTrue((run_dir / "metadata.json").exists())
            self.assertTrue((run_dir / "windows" / "window_1773463600000_1773463610000.csv").exists())


if __name__ == "__main__":
    unittest.main()
