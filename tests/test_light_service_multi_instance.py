import asyncio
import unittest

from common.models import DeviceCommandRequest
from devices.light import main as light_main


class LightServiceMultiInstanceTests(unittest.TestCase):
    def setUp(self) -> None:
        if hasattr(light_main, "state"):
            light_main.state.clear()
            light_main.state.update({"state": "off"})
        if hasattr(light_main, "states"):
            light_main.states.clear()

    def test_light_service_keeps_state_isolated_per_device(self) -> None:
        asyncio.run(light_main.command(DeviceCommandRequest(device_id="light_1", action="turn_on")))
        asyncio.run(light_main.command(DeviceCommandRequest(device_id="light_2", action="turn_off")))

        light_1_state = asyncio.run(light_main.get_state("light_1"))
        light_2_state = asyncio.run(light_main.get_state("light_2"))

        self.assertEqual(light_1_state["state"]["state"], "on")
        self.assertEqual(light_2_state["state"]["state"], "off")


if __name__ == "__main__":
    unittest.main()
