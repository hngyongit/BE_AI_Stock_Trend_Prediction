from __future__ import annotations

from typing import Any

from analyse.prompts.system_prompts import get_system_prompt
from analyse.utils.safe_json import safe_json_dumps


def build_report_prompt(context: dict[str, Any]) -> str:
    return f"""{get_system_prompt()}

JSON CONTEXT:
{safe_json_dumps(context)}
""".strip()
