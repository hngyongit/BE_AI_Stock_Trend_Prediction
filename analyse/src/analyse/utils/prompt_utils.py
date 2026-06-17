from __future__ import annotations


def join_prompt_parts(*parts: str) -> str:
    """Ghep cac phan prompt va bo qua phan rong."""
    return "\n\n".join(part.strip() for part in parts if part and part.strip())
