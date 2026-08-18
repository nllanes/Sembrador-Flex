"""Worker de jobs Sembrar (cola en BD).

Uso:
  python -m scripts.flex_worker

En cloud: FLEX_WORKER_EMBEDDED=false y corre este proceso junto a Appium.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.job_runner import process_one_flex_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [flex-worker] %(levelname)s %(message)s",
)
logger = logging.getLogger("flex_worker")


def run_forever() -> None:
    settings = get_settings()
    poll = max(0.5, float(settings.flex_worker_poll_seconds))
    logger.info("Worker iniciado · poll=%.1fs", poll)
    while True:
        worked = False
        try:
            worked = process_one_flex_job()
        except Exception:
            logger.exception("Error en loop del worker")
        time.sleep(0.2 if worked else poll)


if __name__ == "__main__":
    run_forever()
