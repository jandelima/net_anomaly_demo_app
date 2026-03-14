import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


def load_preview_module():
    script_path = Path(__file__).resolve().parents[1] / "dataset-tools" / "scripts" / "preview_flow_features.py"
    spec = importlib.util.spec_from_file_location("preview_flow_features", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


preview_flow_features = load_preview_module()


class PreviewFlowFeaturesTests(unittest.TestCase):
    def test_valid_devices_include_multiple_instances_per_type(self) -> None:
        self.assertIn("light_2", preview_flow_features.VALID_DEVICES)
        self.assertIn("light_10", preview_flow_features.VALID_DEVICES)
        self.assertIn("lock_2", preview_flow_features.VALID_DEVICES)
        self.assertIn("lock_6", preview_flow_features.VALID_DEVICES)
        self.assertIn("thermostat_2", preview_flow_features.VALID_DEVICES)
        self.assertIn("thermostat_4", preview_flow_features.VALID_DEVICES)

    def test_build_command_payload_can_target_additional_light(self) -> None:
        with patch.object(preview_flow_features.random, "choice", side_effect=["light_3", "turn_on"]):
            payload = preview_flow_features.build_command_payload()

        self.assertEqual(payload["device_id"], "light_3")
        self.assertEqual(payload["action"], "turn_on")


if __name__ == "__main__":
    unittest.main()
