import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from common.config import load_hub_settings
from common.models import HubCommandRequest
from common.rate_limit import InMemoryRateLimiter
from common.validation import validate_command_for_device
from hub.main import command


class RateLimiterAndValidationTests(unittest.TestCase):
    def test_rate_limiter_blocks_after_rpm_limit(self) -> None:
        limiter = InMemoryRateLimiter(rpm=2)

        self.assertTrue(limiter.allow("127.0.0.1"))
        self.assertTrue(limiter.allow("127.0.0.1"))
        self.assertFalse(limiter.allow("127.0.0.1"))

    def test_validate_command_for_device_accepts_valid_action(self) -> None:
        settings = load_hub_settings()
        self.assertIsNone(validate_command_for_device(settings.device_inventory, "light_1", "turn_on"))

    def test_validate_command_for_device_rejects_invalid_action_for_device(self) -> None:
        settings = load_hub_settings()
        error = validate_command_for_device(settings.device_inventory, "lock_1", "turn_on")
        self.assertIsNotNone(error)
        self.assertIn("not valid for device", error)

    def test_validate_command_for_device_rejects_unknown_device(self) -> None:
        settings = load_hub_settings()
        error = validate_command_for_device(settings.device_inventory, "camera_1", "turn_on")
        self.assertEqual(error, "Unknown device_id: camera_1")

    def test_hub_routes_light_2_to_light_service_with_device_id(self) -> None:
        settings = load_hub_settings()
        captured: dict[str, object] = {}

        async def fake_forward_request(request, method: str, url: str, payload=None):
            del request
            captured["method"] = method
            captured["url"] = url
            captured["payload"] = payload
            return 3.14, {"ok": True, "echo_device_id": payload["device_id"]}

        with patch("hub.main.forward_request", side_effect=fake_forward_request):
            response = asyncio.run(
                command(
                    HubCommandRequest(device_id="light_2", action="turn_on", request_id="req-200"),
                    SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(http_client=None))),
                    None,
                    None,
                )
            )

        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["url"], f"{settings.device_inventory['light_2']['base_url']}/command")
        self.assertEqual(captured["payload"], {"device_id": "light_2", "action": "turn_on"})
        self.assertEqual(response["device_id"], "light_2")


if __name__ == "__main__":
    unittest.main()
