from __future__ import annotations

from typing import Any


def validate_command_for_device(
    device_inventory: dict[str, dict[str, Any]],
    device_id: str,
    action: str,
) -> str | None:
    device = device_inventory.get(device_id)
    if device is None:
        return f"Unknown device_id: {device_id}"
    allowed_actions = device["actions"]
    if action not in allowed_actions:
        return f"Action '{action}' is not valid for device '{device_id}'"
    return None
