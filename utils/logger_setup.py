import logging
import os
from pathlib import Path


def setup_logger():
    """
    Configure application logging.
    Logs are written to both console and logs/war.log.
    """

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_file = os.getenv("LOG_FILE", "logs/war.log")

    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                log_file,
                mode="a",
                encoding="utf-8",
            ),
        ],
        force=True,
    )

    logging.info("=" * 80)
    logging.info("WAR Logger Initialized")
    logging.info("=" * 80)