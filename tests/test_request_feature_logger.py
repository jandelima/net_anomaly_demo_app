import csv
import tempfile
import unittest
from pathlib import Path

from common.request_feature_logger import (
    CsvRequestFeatureLogger,
    build_request_preview,
    extract_primary_query_value,
    shannon_entropy,
)


class RequestFeatureLoggerTests(unittest.TestCase):
    def test_shannon_entropy_returns_zero_for_empty_query(self) -> None:
        self.assertEqual(shannon_entropy(""), 0.0)

    def test_build_request_preview_formats_get_with_query(self) -> None:
        preview = build_request_preview(
            method="GET",
            path="/demo/search",
            query="q=lock_1",
            body_data={},
            is_multipart=False,
        )
        self.assertEqual(preview, "GET /demo/search?q=lock_1")

    def test_build_request_preview_formats_post_json(self) -> None:
        preview = build_request_preview(
            method="POST",
            path="/command",
            query="",
            body_data={"device_id": "light_1", "action": "turn_on"},
            is_multipart=False,
        )
        self.assertEqual(preview, 'POST /command {"device_id":"light_1","action":"turn_on"}')

    def test_build_request_preview_formats_post_multipart(self) -> None:
        preview = build_request_preview(
            method="POST",
            path="/demo/upload-preview",
            query="",
            body_data={},
            is_multipart=True,
        )
        self.assertEqual(preview, "POST /demo/upload-preview [multipart]")

    def test_extract_primary_query_value_uses_q_for_search(self) -> None:
        self.assertEqual(extract_primary_query_value("/demo/search", "q=lock_1"), "lock_1")

    def test_extract_primary_query_value_uses_device_id_for_state(self) -> None:
        self.assertEqual(extract_primary_query_value("/state", "device_id=light_1"), "light_1")

    def test_extract_primary_query_value_ignores_irrelevant_query_params(self) -> None:
        self.assertEqual(extract_primary_query_value("/events", "limit=10"), "")

    def test_csv_logger_writes_header_and_row(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "hub_requests.csv"
            logger = CsvRequestFeatureLogger(csv_path)
            logger.log(
                {
                    "timestamp_ms": 1772620878027,
                    "is_error": 0,
                    "is_auth_failure": 0,
                    "path": "/state",
                    "query_length": 17,
                    "query_entropy": 3.22,
                    "request_content_length": 0,
                    "response_length": 42,
                    "request_preview": "GET /state?device_id=light_1",
                }
            )

            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["path"], "/state")
        self.assertEqual(rows[0]["request_content_length"], "0")
        self.assertEqual(rows[0]["response_length"], "42")
        self.assertEqual(rows[0]["request_preview"], "GET /state?device_id=light_1")


if __name__ == "__main__":
    unittest.main()
