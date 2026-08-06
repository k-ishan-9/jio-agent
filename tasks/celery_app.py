"""
tasks/celery_app.py — Celery application initialization and Beat schedule.
"""

from celery import Celery
from celery.schedules import crontab
from config import REDIS_URL

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

if __name__ == "__main__":
    app.start()
