"""Worker embebido (hilo daemon) para desarrollo local."""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)
_started = False


def start_embedded_worker() -> None:
    global _started
    from app.config import get_settings

    settings = get_settings()
    if not settings.flex_worker_embedded:
        logger.info("Worker embebido desactivado (usa python -m scripts.flex_worker)")
        return
    if _started:
        return
    _started = True

    def _loop() -> None:
        from app.database import SessionLocal
        from app.job_runner import process_one_flex_job
        from app import crud

        # Tras --reload: reencolar jobs recientes; fallar solo huérfanos muy viejos.
        db = SessionLocal()
        try:
            requeued, failed = crud.recover_interrupted_running_jobs(db)
            if requeued or failed:
                logger.warning(
                    "Jobs tras reinicio: reencolados=%s fallidos_huérfanos=%s",
                    requeued,
                    failed,
                )
        finally:
            db.close()

        poll = max(0.5, float(settings.flex_worker_poll_seconds))
        logger.info("Worker embebido activo · poll=%.1fs", poll)
        while True:
            try:
                worked = process_one_flex_job()
            except Exception:
                logger.exception("Worker embebido: error")
                worked = False
            time.sleep(0.25 if worked else poll)

    threading.Thread(target=_loop, name="flex-worker", daemon=True).start()
