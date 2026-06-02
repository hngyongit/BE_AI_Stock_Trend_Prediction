from __future__ import annotations

import logging


def configure_logging(level: int = logging.INFO) -> None:
    """Configure process-wide logging once."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
