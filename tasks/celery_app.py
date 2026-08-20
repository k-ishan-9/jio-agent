"""
tasks/celery_app.py — Celery application initialization and Beat schedule.
"""

import json
import logging
import time

from celery import Celery
from celery.schedules import crontab
from celery.signals import task_failure

from config import REDIS_URL, DATA_ROOT

logger = logging.getLogger("jio_pipeline")

DEAD_LETTER_PATH = DATA_ROOT / "dead_letter_tasks.jsonl"

app = Celery(
    "jio_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks.pipeline"],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Only ack a task after it completes (success or exhausted retries), so a
    # worker crash mid-task re-delivers it instead of silently dropping it.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    beat_schedule={
        "check-plan-changes-hourly": {
            "task": "tasks.pipeline.check_plan_changes",
            "schedule": 3600.0,  # Every 1 hour
        },
        "check-faq-changes-weekly": {
            "task": "tasks.pipeline.check_faq_changes",
            "schedule": 604800.0,  # Every 7 days
        },
    },
)


@task_failure.connect
def _record_dead_letter(sender=None, task_id=None, exception=None, args=None, kwargs=None, **_):
    """Called once a task has exhausted all its retries. There's no
    dedicated alerting pipeline here, so this at minimum guarantees a
    permanently-failed re-ingestion is durably recorded (not just a log
    line that scrolls away) for someone to find and act on."""
    entry = {
        "timestamp": time.time(),
        "task_id": task_id,
        "task_name": getattr(sender, "name", str(sender)),
        "args": args,
        "kwargs": kwargs,
        "exception": str(exception),
    }
    try:
        DEAD_LETTER_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DEAD_LETTER_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Failed to write dead-letter entry: {e}")
    logger.error(f"Task permanently failed after retries: {entry}")


if __name__ == "__main__":
    app.start()
