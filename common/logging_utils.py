from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class JsonLineLogger:
    """Small JSONL logger for low-resource environments."""

    def __init__(self, service: str, log_to_file: bool = False, file_path: Path | None = None) -> None:
        self.service = service
        self.log_to_file = log_to_file
        self.file_path = file_path
        self._lock = threading.Lock()
        if self.log_to_file and self.file_path is not None:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, payload: dict[str, Any]) -> None:
        entry = dict(payload)
        entry.setdefault("ts", utc_now_iso())
        entry.setdefault("service", self.service)
        line = json.dumps(entry, separators=(",", ":"), ensure_ascii=True)
        print(line, flush=True)
        if self.log_to_file and self.file_path is not None:
            with self._lock:
                with self.file_path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")

