from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


@dataclass(frozen=True)
class HubSettings:
    version: str
    api_key: str
    request_timeout_seconds: float
    rate_limit_enabled: bool
    rate_limit_rpm: int
    data_dir: Path
    firmware_dir: Path
    log_to_file: bool
    log_file_path: Path
    device_urls: dict[str, str]


@dataclass(frozen=True)
class DeviceSettings:
    hub_url: str
    request_timeout_seconds: float


def load_hub_settings() -> HubSettings:
    data_dir = Path(os.getenv("HUB_DATA_DIR", "./data"))
    return HubSettings(
        version=os.getenv("HUB_VERSION", "0.1.0"),
        api_key=os.getenv("HUB_API_KEY", "devkey"),
        request_timeout_seconds=float(os.getenv("HUB_REQUEST_TIMEOUT_SECONDS", "2.0")),
        rate_limit_enabled=env_bool("HUB_RATE_LIMIT_ENABLED", default=False),
        rate_limit_rpm=env_int("HUB_RATE_LIMIT_RPM", 60),
        data_dir=data_dir,
        firmware_dir=data_dir / "firmware",
        log_to_file=env_bool("HUB_LOG_TO_FILE", default=False),
        log_file_path=data_dir / "logs" / "hub.jsonl",
        device_urls={
            "light_1": os.getenv("HUB_LIGHT_URL", "http://localhost:8001"),
            "lock_1": os.getenv("HUB_LOCK_URL", "http://localhost:8002"),
            "thermostat_1": os.getenv("HUB_THERMOSTAT_URL", "http://localhost:8003"),
        },
    )


def load_device_settings() -> DeviceSettings:
    return DeviceSettings(
        hub_url=os.getenv("HUB_URL", "http://localhost:8000"),
        request_timeout_seconds=float(os.getenv("DEVICE_REQUEST_TIMEOUT_SECONDS", "2.0")),
    )

