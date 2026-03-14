import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from starlette.requests import Request
from starlette.responses import Response

from hub import main as hub_main


def make_request(
    method: str,
    path: str,
    query: str = "",
    body: bytes = b"",
    content_type: str = "application/json",
) -> Request:
    async def receive() -> dict[str, object]:
        nonlocal body
        chunk = body
        body = b""
        return {"type": "http.request", "body": chunk, "more_body": False}

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": query.encode("utf-8"),
        "headers": [
            (b"content-type", content_type.encode("ascii")),
            (b"content-length", str(len(body)).encode("ascii")),
        ],
        "client": ("127.0.0.1", 12345),
        "app": hub_main.app,
    }
    return Request(scope, receive)


class HubRequestFeaturesTests(unittest.TestCase):
    def test_middleware_logs_state_request_features(self) -> None:
        request = make_request("GET", "/state", "device_id=light_1")
        captured: list[dict[str, object]] = []

        async def call_next(_request: Request) -> Response:
            return Response(status_code=200)

        with patch.object(hub_main, "app_feature_logger", new=SimpleNamespace(log=lambda row: captured.append(row))):
            asyncio.run(hub_main.request_logging_middleware(request, call_next))

        self.assertEqual(len(captured), 1)
        row = captured[0]
        self.assertEqual(row["is_error"], 0)
        self.assertEqual(row["is_auth_failure"], 0)
        self.assertEqual(row["path"], "/state")
        self.assertEqual(row["query_length"], len("light_1"))
        self.assertEqual(row["request_content_length"], 0)
        self.assertEqual(row["response_length"], 0)
        self.assertEqual(row["request_preview"], "GET /state?device_id=light_1")

    def test_middleware_logs_command_request_preview(self) -> None:
        body = json.dumps({"device_id": "light_1", "action": "turn_on", "request_id": "req-1"}).encode("utf-8")
        request = make_request("POST", "/command", body=body)
        captured: list[dict[str, object]] = []

        async def call_next(_request: Request) -> Response:
            return Response(status_code=200)

        with patch.object(hub_main, "app_feature_logger", new=SimpleNamespace(log=lambda row: captured.append(row))):
            asyncio.run(hub_main.request_logging_middleware(request, call_next))

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["request_content_length"], len(body))
        self.assertEqual(captured[0]["response_length"], 0)
        self.assertEqual(
            captured[0]["request_preview"],
            'POST /command {"device_id":"light_1","action":"turn_on","request_id":"req-1"}',
        )

    def test_middleware_marks_auth_failure(self) -> None:
        request = make_request("GET", "/state", "device_id=light_1")
        captured: list[dict[str, object]] = []

        async def call_next(_request: Request) -> Response:
            return Response(status_code=401)

        with patch.object(hub_main, "app_feature_logger", new=SimpleNamespace(log=lambda row: captured.append(row))):
            asyncio.run(hub_main.request_logging_middleware(request, call_next))

        self.assertEqual(captured[0]["is_error"], 1)
        self.assertEqual(captured[0]["is_auth_failure"], 1)

    def test_middleware_marks_multipart_preview(self) -> None:
        request = make_request("POST", "/demo/upload-preview", content_type="multipart/form-data; boundary=abc")
        captured: list[dict[str, object]] = []

        async def call_next(_request: Request) -> Response:
            return Response(status_code=200)

        with patch.object(hub_main, "app_feature_logger", new=SimpleNamespace(log=lambda row: captured.append(row))):
            asyncio.run(hub_main.request_logging_middleware(request, call_next))

        self.assertEqual(captured[0]["request_preview"], "POST /demo/upload-preview [multipart]")
        self.assertEqual(captured[0]["query_length"], 0)
        self.assertEqual(captured[0]["query_entropy"], 0.0)
        self.assertEqual(captured[0]["request_content_length"], 0)
        self.assertEqual(captured[0]["response_length"], 0)


if __name__ == "__main__":
    unittest.main()
