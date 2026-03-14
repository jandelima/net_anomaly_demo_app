from __future__ import annotations

import json
import time
import subprocess
from typing import Any, Callable

from flask import Flask, request
from jinja2 import Environment


def create_demo_app(search_provider: Callable[[str], dict[str, Any]]) -> Flask:
    demo_app = Flask(__name__)

    @demo_app.route("/search")
    def search():
        query = request.args.get("q", "")

        # Intentionally mirrors the demonstration snippet behavior.
        env = Environment()
        template = env.from_string(f"Resultado para: {query}")
        result = template.render(config=demo_app.config)

        search_payload = search_provider(query)
        rendered_payload = json.dumps(search_payload, indent=2, ensure_ascii=True)
        return f"<pre>{result}\n\n{rendered_payload}</pre>"

    @demo_app.route("/upload-preview", methods=["POST"])
    def upload_preview():
        started = time.perf_counter()

        # Accessing form/files triggers multipart parsing inside Werkzeug.
        form_fields = request.form
        uploaded_files = request.files

        parsed_field_count = sum(len(values) for _, values in form_fields.lists())
        parse_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "ok": True,
            "parsed_field_count": parsed_field_count,
            "parsed_file_count": len(uploaded_files),
            "parse_ms": parse_ms,
        }

    return demo_app
