from __future__ import annotations

import csv
import json
import math
import threading
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs
from typing import Any


CSV_FIELDNAMES = (
    "timestamp_ms",
    "is_error",
    "is_auth_failure",
    "path",
    "query_length",
    "query_entropy",
    "request_content_length",
    "response_length",
    "request_preview",
)


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    total = len(value)
    entropy = 0.0
    for count in counts.values():
        probability = count / total
        entropy -= probability * math.log2(probability)
    return round(entropy, 4)


def extract_primary_query_value(path: str, query: str) -> str:
    if not query:
        return ""
    parsed = parse_qs(query, keep_blank_values=True)
    if path == "/demo/search":
        return parsed.get("q", [""])[0]
    if path == "/state":
        return parsed.get("device_id", [""])[0]
    return ""


def build_request_preview(
    method: str,
    path: str,
    query: str,
    body_data: dict[str, Any],
    is_multipart: bool,
) -> str:
    normalized_method = method.upper()
    if normalized_method == "GET":
        return f"{normalized_method} {path}?{query}" if query else f"{normalized_method} {path}"
    if is_multipart:
        return f"{normalized_method} {path} [multipart]"
    if body_data:
        compact_json = json.dumps(body_data, separators=(",", ":"), ensure_ascii=True)
        return f"{normalized_method} {path} {compact_json}"
    return f"{normalized_method} {path}"


class CsvRequestFeatureLogger:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self._lock = threading.Lock()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, row: dict[str, Any]) -> None:
        normalized_row = {field: row.get(field, "") for field in CSV_FIELDNAMES}
        with self._lock:
            needs_header = not self.file_path.exists() or self.file_path.stat().st_size == 0
            with self.file_path.open("a", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
                if needs_header:
                    writer.writeheader()
                writer.writerow(normalized_row)
