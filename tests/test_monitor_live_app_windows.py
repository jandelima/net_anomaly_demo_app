import unittest

from dataset_tools_import_helper import load_script_module


monitor_live_app_windows = load_script_module(
    "monitor_live_app_windows",
    "dataset-tools/scripts/monitor_live_app_windows.py",
)


class MonitorLiveAppWindowsTests(unittest.TestCase):
    def test_compute_window_bounds_uses_fixed_10s_bucket(self) -> None:
        self.assertEqual(
            monitor_live_app_windows.compute_window_bounds(1773541387531, 10),
            (1773541380000, 1773541390000),
        )


if __name__ == "__main__":
    unittest.main()
