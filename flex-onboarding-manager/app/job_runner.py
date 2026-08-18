"""Procesamiento de jobs Sembrar (compartido por worker embebido y CLI)."""

from __future__ import annotations

import logging

from app import crud
from app.database import SessionLocal
from app.enums import EventType

logger = logging.getLogger(__name__)


def process_one_flex_job() -> bool:
    """Procesa un job queued si existe. Devuelve True si trabajó."""
    db = SessionLocal()
    try:
        job = crud.claim_next_flex_job(db)
        if job is None:
            return False
        job_id = job.id
        candidate_ids = list(job.candidate_ids or [])
        actor = job.actor
        logger.info("Job %s · %s candidato(s)", job_id, len(candidate_ids))

        def on_progress(msg: str) -> None:
            j = crud.get_flex_job(db, job_id)
            if j is None:
                return
            j.message = msg[:500]
            db.commit()
            logger.info("Job %s · %s", job_id, msg)

        try:
            # Sesión aparte para el dispatch (commits propios)
            work = SessionLocal()
            try:
                result = crud.batch_dispatch_flex(
                    work,
                    candidate_ids=candidate_ids,
                    actor=actor,
                    on_progress=on_progress,
                )
            finally:
                work.close()
            job = crud.get_flex_job(db, job_id)
            if job is None:
                return True
            crud.complete_flex_job(db, job, result=result)
            for skip in result.skipped_items:
                logger.warning(
                    "Job %s SKIP · %s · %s",
                    job_id,
                    skip.assigned_email or skip.id,
                    skip.reason,
                )
            logger.info(
                "Job %s OK · dispatched=%s skipped=%s",
                job_id,
                result.dispatched,
                result.skipped,
            )
        except Exception as exc:
            logger.exception("Job %s falló", job_id)
            job = crud.get_flex_job(db, job_id)
            if job is not None:
                crud.complete_flex_job(db, job, error=str(exc))
                for cid in candidate_ids:
                    cand = crud.get_candidate(db, int(cid))
                    if cand is None:
                        continue
                    crud._log_event(
                        db,
                        cand,
                        EventType.NOTE_ADDED,
                        message=f"Sembrar falló (job {job_id[:8]}…): {exc}",
                        actor=actor,
                    )
                db.commit()
        return True
    finally:
        db.close()
