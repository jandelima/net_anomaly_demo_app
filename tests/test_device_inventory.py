import unittest

from common.config import load_hub_settings
from common.validation import validate_command_for_device


class DeviceInventoryTests(unittest.TestCase):
    def test_load_hub_settings_exposes_requested_device_counts(self) -> None:
        settings = load_hub_settings()

        light_devices = [device for device in settings.device_inventory.values() if device["type"] == "light"]
        lock_devices = [device for device in settings.device_inventory.values() if device["type"] == "lock"]
        thermostat_devices = [
            device for device in settings.device_inventory.values() if device["type"] == "thermostat"
        ]

        self.assertEqual(len(light_devices), 10)
        self.assertEqual(len(lock_devices), 6)
        self.assertEqual(len(thermostat_devices), 4)

    def test_validate_command_for_device_uses_inventory_actions(self) -> None:
        settings = load_hub_settings()

        self.assertIsNone(validate_command_for_device(settings.device_inventory, "light_2", "turn_on"))

        error = validate_command_for_device(settings.device_inventory, "light_2", "unlock")
        self.assertIsNotNone(error)
        self.assertIn("not valid for device", error)


if __name__ == "__main__":
    unittest.main()
