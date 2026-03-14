import asyncio
import unittest
from unittest.mock import patch

from common.models import DeviceCommandRequest
from devices.thermostat import main as thermostat_main


class ThermostatServiceMultiInstanceTests(unittest.TestCase):
    def setUp(self) -> None:
        if hasattr(thermostat_main, "state"):
            thermostat_main.state.clear()
            thermostat_main.state.update(
                {
                    "temp": 22.0,
                    "mode": "off",
                    "setpoint": 22.0,
                    "humidity": 45.0,
                    "fan_speed": "auto",
                    "sensor_health": "ok",
                    "battery_pct": 96.5,
                    "last_updated": thermostat_main.utc_now_iso(),
                }
            )
        if hasattr(thermostat_main, "states"):
            thermostat_main.states.clear()

    def test_thermostat_service_keeps_state_isolated_per_device(self) -> None:
        with patch("devices.thermostat.main.asyncio.sleep", new=self._immediate_sleep):
            asyncio.run(
                thermostat_main.command(DeviceCommandRequest(device_id="thermostat_1", action="set_temp", value=19))
            )
            asyncio.run(
                thermostat_main.command(DeviceCommandRequest(device_id="thermostat_2", action="set_temp", value=25))
            )

        thermostat_1_state = asyncio.run(thermostat_main.get_state("thermostat_1"))
        thermostat_2_state = asyncio.run(thermostat_main.get_state("thermostat_2"))

        self.assertEqual(thermostat_1_state["state"]["setpoint"], 19.0)
        self.assertEqual(thermostat_2_state["state"]["setpoint"], 25.0)

    async def _immediate_sleep(self, *_args, **_kwargs) -> None:
        return None


if __name__ == "__main__":
    unittest.main()
