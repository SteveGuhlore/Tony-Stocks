from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(log_dir: str | Path = "logs") -> None:
    """Configure console and file logging for scanner runs."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(Path(log_dir) / "trading_bot.log", encoding="utf-8"),
        ],
        force=True,
    )

