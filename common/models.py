from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

class HubCommandRequest(BaseModel):
    device_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    value: Any | None = None
    request_id: str | None = None


class DeviceCommandRequest(BaseModel):
    action: str = Field(min_length=1)
    value: Any | None = None


class HubEventRequest(BaseModel):
    device_id: str = Field(min_length=1)
    event: str = Field(min_length=1)
    value: Any | None = None
    ts: str | None = None


class DeviceEmitEventRequest(BaseModel):
    event: str = Field(min_length=1)
    value: Any | None = None
