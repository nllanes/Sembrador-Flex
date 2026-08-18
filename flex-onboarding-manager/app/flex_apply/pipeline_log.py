"""Logger de pipeline Sembrar → archivo + buffer para el modal/timeline."""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("sembrar.pipeline")

EVIDENCE_DIR = Path(__file__).resolve().parent.parent.parent / "var" / "flex_apply"

_local = threading.local()


def _safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", value)[:80]


def begin_pipeline_log(email: str) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"{_safe_slug(email)}_pipeline.log"
    path.write_text("", encoding="utf-8")
    _local.path = path
    _local.lines = []
    step(f"=== Sembrar pipeline start email={email} ===")
    return path


def step(msg: str, *, level: int = logging.INFO) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    logger.log(level, msg)
    lines = getattr(_local, "lines", None)
    if lines is not None:
        lines.append(line)
    path = getattr(_local, "path", None)
    if path is not None:
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:
            pass


def pipeline_tail(max_lines: int = 12) -> str:
    lines = getattr(_local, "lines", None) or []
    if not lines:
        return ""
    return " | ".join(lines[-max_lines:])


def pipeline_path() -> str | None:
    path = getattr(_local, "path", None)
    return str(path) if path else None
