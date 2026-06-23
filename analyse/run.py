from __future__ import annotations

import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from analyse.config.settings import get_settings
from analyse.utils.asyncio_windows import ensure_windows_proactor_event_loop_policy


def main() -> None:
    """Chạy FastAPI analyse service."""
    ensure_windows_proactor_event_loop_policy()
    load_dotenv(ROOT / ".env")
    settings = get_settings()
    uvicorn.run(
        "analyse.main:app",
        host=settings.analyse_host,
        port=settings.analyse_port,
        reload=settings.analyse_env == "development",
    )


if __name__ == "__main__":
    main()
