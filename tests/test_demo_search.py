import unittest

from fastapi.routing import Mount

from hub.demo_flask import create_demo_app
from hub.main import app, demo_search_records, runtime


class DemoSearchEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        runtime.recent_events.clear()

    def test_demo_search_records_returns_matching_event(self) -> None:
        runtime.recent_events.append(
            {
                "device_id": "light_1",
                "event": "motion_detected",
                "value": {"zone": "kitchen"},
                "ts": "2026-03-10T10:00:00.000Z",
            }
        )

        search_payload = demo_search_records("motion_detected")
        rendered_payload = str(search_payload)
        self.assertIn("motion_detected", rendered_payload)
        self.assertIn("light_1", rendered_payload)

    def test_demo_search_records_returns_matching_device(self) -> None:
        search_payload = demo_search_records("lock_1")
        self.assertIn({"device_id": "lock_1", "base_url": "http://localhost:8002"}, search_payload["matched_devices"])

    def test_demo_upload_preview_reports_parsing_metrics(self) -> None:
        demo_app = create_demo_app(lambda q: {"query": q, "matched_devices": []})
        client = demo_app.test_client()
        response = client.post(
            "/upload-preview",
            data={f"field_{idx}": "x" for idx in range(40)},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertGreaterEqual(payload["parsed_field_count"], 40)
        self.assertIn("parse_ms", payload)

    def test_demo_search_renders_jinja_expression_for_demo(self) -> None:
        demo_app = create_demo_app(lambda q: {"query": q, "matched_devices": [{"device_id": "lock_1"}]})
        client = demo_app.test_client()
        search = client.get("/search?q={{7*7}}")
        self.assertEqual(search.status_code, 200)
        text = search.get_data(as_text=True)
        self.assertIn("Resultado para: 49", text)
        self.assertIn("\"device_id\": \"lock_1\"", text)

    def test_hub_mounts_demo_wsgi_app(self) -> None:
        has_demo_mount = any(isinstance(route, Mount) and route.path == "/demo" for route in app.routes)
        self.assertTrue(has_demo_mount)


if __name__ == "__main__":
    unittest.main()
