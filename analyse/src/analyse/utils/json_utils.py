from __future__ import annotations

import json
from typing import Any


def safe_json_dumps(value: Any) -> str:
    """Chuyen object sang JSON string de dua vao prompt trong giai doan sau."""
    return json.dumps(value, ensure_ascii=False, default=str)
