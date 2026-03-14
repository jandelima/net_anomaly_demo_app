import asyncio
import unittest
from unittest.mock import patch

from common.models import DeviceCommandRequest
from devices.lock import main as lock_main


class LockServiceMultiInstanceTests(unittest.TestCase):
    def setUp(self) -> None:
        if hasattr(lock_main, "state"):
            lock_main.state.clear()
            lock_main.state.update({"state": "locked"})
        if hasattr(lock_main, "states"):
            lock_main.states.clear()

    def test_lock_service_keeps_state_isolated_per_device(self) -> None:
        with patch("devices.lock.main.asyncio.sleep", new=self._immediate_sleep):
            asyncio.run(lock_main.command(DeviceCommandRequest(device_id="lock_1", action="unlock")))
            asyncio.run(lock_main.command(DeviceCommandRequest(device_id="lock_2", action="lock")))

        lock_1_state = asyncio.run(lock_main.get_state("lock_1"))
        lock_2_state = asyncio.run(lock_main.get_state("lock_2"))

        self.assertEqual(lock_1_state["state"]["state"], "unlocked")
        self.assertEqual(lock_2_state["state"]["state"], "locked")

    async def _immediate_sleep(self, *_args, **_kwargs) -> None:
        return None


if __name__ == "__main__":
    unittest.main()
