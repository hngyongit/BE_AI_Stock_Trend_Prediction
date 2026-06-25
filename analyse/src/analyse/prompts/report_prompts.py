from __future__ import annotations

from typing import Any

from analyse.prompts.json_schema_prompts import build_json_schema_instruction
from analyse.prompts.system_prompts import get_system_prompt
from analyse.utils.safe_json import safe_json_dumps


def build_report_prompt(context: dict[str, Any], schema: dict[str, Any] | None = None) -> str:
    schema_instruction = build_json_schema_instruction(schema)
    return f"""{get_system_prompt()}

OUTPUT REQUIREMENTS:
{schema_instruction}

MANDATORY OUTPUT REQUIREMENTS:

1. scenarios:
   Return exactly 3 scenarios:
   - Tích cực
   - Cơ sở
   - Thận trọng

   Each scenario must include:
   - scenario
   - probability_pct
   - time_horizon
   - condition
   - expected_behavior
   - supporting_signals
   - invalidation_signals
   - risk_note

2. checklist:
   Return at least 5 checklist items.
   Each item must include:
   - label
   - status
   - note
   - source_basis

3. action_plan:
   Return:
   - at least 2 short_term actions
   - at least 2 medium_term actions
   - at least 3 watch_points
   - at least 3 risk_management items

4. Do not output empty arrays for these sections.

5. Do not use "Chưa xác minh", "Chưa xác định", "Không có dữ liệu", "Không đủ dữ liệu", "N/A", "unknown", "null", or "undefined" as qualitative content.

6. If numeric values are missing, set numeric fields to null and provide a specific limitation note.

7. Always produce a useful forecast-oriented report from the available evidence.

JSON CONTEXT:
{safe_json_dumps(context)}
""".strip()
