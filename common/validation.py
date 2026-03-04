from __future__ import annotations

DEVICE_ACTIONS: dict[str, set[str]] = {
    "light_1": {"turn_on", "turn_off"},
    "lock_1": {"lock", "unlock"},
    "thermostat_1": {"set_temp"},
}


def validate_command_for_device(device_id: str, action: str) -> str | None:
    allowed_actions = DEVICE_ACTIONS.get(device_id)
    if allowed_actions is None:
        return f"Unknown device_id: {device_id}"
    if action not in allowed_actions:
        return f"Action '{action}' is not valid for device '{device_id}'"
    return None

