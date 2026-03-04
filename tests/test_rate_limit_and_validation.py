import unittest

from common.rate_limit import InMemoryRateLimiter
from common.validation import validate_command_for_device


class RateLimiterAndValidationTests(unittest.TestCase):
    def test_rate_limiter_blocks_after_rpm_limit(self) -> None:
        limiter = InMemoryRateLimiter(rpm=2)

        self.assertTrue(limiter.allow("127.0.0.1"))
        self.assertTrue(limiter.allow("127.0.0.1"))
        self.assertFalse(limiter.allow("127.0.0.1"))

    def test_validate_command_for_device_accepts_valid_action(self) -> None:
        self.assertIsNone(validate_command_for_device("light_1", "turn_on"))

    def test_validate_command_for_device_rejects_invalid_action_for_device(self) -> None:
        error = validate_command_for_device("lock_1", "turn_on")
        self.assertIsNotNone(error)
        self.assertIn("not valid for device", error)

    def test_validate_command_for_device_rejects_unknown_device(self) -> None:
        error = validate_command_for_device("camera_1", "turn_on")
        self.assertEqual(error, "Unknown device_id: camera_1")


if __name__ == "__main__":
    unittest.main()
