import logging
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def setup_logger():
    """
    Configure application logging.

    A new log file is created for every execution.
    Example:
        logs/war_20260716_143025.log
    """

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"war_{datetime.now():%Y%m%d_%H%M%S}.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(
        log_file,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        handlers=[
            console_handler,
            file_handler,
        ],
        force=True,
    )

    logging.info("=" * 80)
    logging.info("WAR Logger Initialized")
    logging.info(f"Log Level : {log_level}")
    logging.info(f"Log File  : {log_file}")
    logging.info("=" * 80)