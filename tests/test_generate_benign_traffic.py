import os
import subprocess
import importlib.util
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
from random import Random


def load_generator_module():
    script_path = Path(__file__).resolve().parents[1] / "dataset-tools" / "scripts" / "generate_benign_traffic.py"
    spec = importlib.util.spec_from_file_location("generate_benign_traffic", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


generator = load_generator_module()


class GenerateBenignTrafficTests(unittest.TestCase):
    def test_cli_starts_without_module_import_error(self) -> None:
        script_path = Path(__file__).resolve().parents[1] / "dataset-tools" / "scripts" / "generate_benign_traffic.py"
        env = dict(os.environ)
        env["PYTHONPATH"] = ""
        result = subprocess.run(
            [
                str(Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python"),
                str(script_path),
                "--hub-url",
                "http://127.0.0.1:1",
                "--duration-seconds",
                "0",
                "--request-timeout-seconds",
                "0.2",
            ],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertNotIn("ModuleNotFoundError", result.stderr)
        self.assertNotEqual(result.returncode, 0)

    def test_mode_specs_match_approved_configuration(self) -> None:
        self.assertEqual(generator.MODE_SPECS["idle"].weight, 0.20)
        self.assertEqual(generator.MODE_SPECS["idle"].duration_range_seconds, (12.0, 45.0))
        self.assertIsNone(generator.MODE_SPECS["idle"].interval_range_seconds)

        self.assertEqual(generator.MODE_SPECS["sparse"].weight, 0.25)
        self.assertEqual(generator.MODE_SPECS["sparse"].duration_range_seconds, (20.0, 90.0))
        self.assertEqual(generator.MODE_SPECS["sparse"].interval_range_seconds, (8.0, 25.0))

        self.assertEqual(generator.MODE_SPECS["normal"].weight, 0.45)
        self.assertEqual(generator.MODE_SPECS["normal"].duration_range_seconds, (30.0, 180.0))
        self.assertEqual(generator.MODE_SPECS["normal"].interval_range_seconds, (1.5, 4.0))

        self.assertEqual(generator.MODE_SPECS["busy"].weight, 0.10)
        self.assertEqual(generator.MODE_SPECS["busy"].duration_range_seconds, (8.0, 30.0))
        self.assertEqual(generator.MODE_SPECS["busy"].interval_range_seconds, (0.2, 1.2))

    def test_endpoint_weights_match_approved_distribution(self) -> None:
        expected_weights = {
            "/command": 0.38,
            "/state": 0.24,
            "/health": 0.12,
            "/event": 0.08,
            "/events": 0.06,
            "/firmware": 0.02,
            "/demo/search": 0.07,
            "/demo/upload-preview": 0.03,
        }
        self.assertEqual(generator.ENDPOINT_WEIGHTS, expected_weights)
        self.assertAlmostEqual(sum(generator.ENDPOINT_WEIGHTS.values()), 1.0)

    def test_build_command_request_for_thermostat_is_valid(self) -> None:
        spec = generator.build_request_spec(Random(7), endpoint="/command")

        self.assertEqual(spec.method, "POST")
        self.assertEqual(spec.path, "/command")
        self.assertIn("X-API-Key", spec.headers)
        self.assertIsNotNone(spec.json_body)
        self.assertIn(spec.json_body["device_id"], generator.DEVICE_INVENTORY)
        self.assertTrue(spec.json_body["request_id"].startswith("benign-"))

    def test_build_firmware_request_uses_fixed_filename(self) -> None:
        spec = generator.build_request_spec(Random(11), endpoint="/firmware")

        self.assertEqual(spec.method, "POST")
        self.assertEqual(spec.path, "/firmware")
        self.assertIsNotNone(spec.multipart_fields)
        file_fields = [field for field in spec.multipart_fields if field[0] == "file"]
        self.assertEqual(len(file_fields), 1)
        file_name = file_fields[0][1][0]
        self.assertEqual(file_name, "firmware_preview.bin")

    def test_build_search_request_uses_whitelisted_queries(self) -> None:
        spec = generator.build_request_spec(Random(13), endpoint="/demo/search")

        self.assertEqual(spec.method, "GET")
        self.assertEqual(spec.path, "/demo/search")
        self.assertEqual(set(spec.params.keys()), {"q"})
        self.assertIn(spec.params["q"], generator.SEARCH_QUERY_WHITELIST)

    def test_build_upload_preview_request_uses_support_fields(self) -> None:
        spec = generator.build_request_spec(Random(17), endpoint="/demo/upload-preview")

        self.assertEqual(spec.method, "POST")
        self.assertEqual(spec.path, "/demo/upload-preview")
        self.assertIsNotNone(spec.multipart_fields)
        field_names = [field[0] for field in spec.multipart_fields]
        self.assertIn("device_id", field_names)
        self.assertIn("ticket", field_names)
        self.assertIn("note", field_names)
        attachment_fields = [field for field in spec.multipart_fields if field[0] == "attachment"]
        self.assertLessEqual(len(attachment_fields), 1)


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None


class _FakeAsyncClient:
    def __init__(self, clock: _FakeClock, timeout: float) -> None:
        self.clock = clock
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, url: str):
        return _FakeResponse()


class GenerateBenignTrafficAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_benign_traffic_recreates_client_for_each_non_idle_mode(self) -> None:
        clock = _FakeClock()
        created_clients = []
        request_client_ids = []

        def client_factory(*, timeout: float):
            client = _FakeAsyncClient(clock, timeout)
            created_clients.append(client)
            return client

        async def fake_send_request(client, hub_url, request_spec):
            del hub_url, request_spec
            request_client_ids.append(id(client))
            clock.now += 0.011
            return 200

        with patch.object(generator.httpx, 'AsyncClient', side_effect=client_factory),             patch.object(generator, 'sample_mode', side_effect=['normal', 'busy', 'idle']),             patch.object(generator, 'sample_duration_seconds', side_effect=[0.01, 0.01, 0.02]),             patch.object(generator, 'sample_interval_seconds', return_value=1.0),             patch.object(generator, 'send_request', side_effect=fake_send_request),             patch.object(generator.time, 'monotonic', side_effect=clock.monotonic),             patch.object(generator.asyncio, 'sleep', side_effect=clock.sleep):
            metrics = await generator.run_benign_traffic(
                hub_url='http://localhost:8000',
                api_key='devkey',
                duration_seconds=0.03,
                request_timeout_seconds=5.0,
                seed=7,
            )

        self.assertEqual(metrics.total_requests, 2)
        self.assertEqual(len(set(request_client_ids)), 2)
        self.assertEqual(len(created_clients), 3)


if __name__ == "__main__":
    unittest.main()
