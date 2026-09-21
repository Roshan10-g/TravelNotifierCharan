"""
Dynamic per-user scheduler using APScheduler (AsyncIOScheduler).
Schedules morning & evening commute prompts based on each user's custom preferences.
Supports 30-minute snooze jobs.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timedelta
import pytz
import logging
import database
import config

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=pytz.timezone(config.TIMEZONE))


def get_cron_day_string(active_days: str) -> str:
    """Converts comma-separated days (e.g. 'mon,tue,wed,thu,fri') to valid cron expression."""
    clean = active_days.strip().lower()
    return clean if clean else "mon-fri"


def schedule_user_commute(bot, user_id: int, send_prompt_func):
    """
    Registers or updates the dynamic cron jobs for a specific user:
    - Morning job at user's morning_time
    - Evening job at user's evening_time
    """
    user = database.get_or_create_user(user_id)
    m_time = user.get("morning_time", "08:00")
    e_time = user.get("evening_time", "18:30")
    days = get_cron_day_string(user.get("active_days", "mon,tue,wed,thu,fri"))

    tz = pytz.timezone(config.TIMEZONE)

    try:
        m_hour, m_min = map(int, m_time.split(":"))
        m_job_id = f"morning_{user_id}"
        scheduler.add_job(
            send_prompt_func,
            trigger=CronTrigger(hour=m_hour, minute=m_min, day_of_week=days, timezone=tz),
            id=m_job_id,
            args=[user_id, "morning"],
            replace_existing=True
        )
        logger.info(f"Scheduled morning prompt for user {user_id} at {m_time} on {days}")
    except Exception as e:
        logger.error(f"Failed to schedule morning job for {user_id}: {e}")

    try:
        e_hour, e_min = map(int, e_time.split(":"))
        e_job_id = f"evening_{user_id}"
        scheduler.add_job(
            send_prompt_func,
            trigger=CronTrigger(hour=e_hour, minute=e_min, day_of_week=days, timezone=tz),
            id=e_job_id,
            args=[user_id, "evening"],
            replace_existing=True
        )
        logger.info(f"Scheduled evening prompt for user {user_id} at {e_time} on {days}")
    except Exception as e:
        logger.error(f"Failed to schedule evening job for {user_id}: {e}")


def snooze_user_prompt(user_id: int, direction: str, send_prompt_func, minutes: int = 30):
    """
    Snoozes the commute prompt by scheduling a one-shot notification in X minutes.
    """
    tz = pytz.timezone(config.TIMEZONE)
    run_date = datetime.now(tz) + timedelta(minutes=minutes)
    snooze_job_id = f"snooze_{user_id}_{direction}"

    scheduler.add_job(
        send_prompt_func,
        trigger=DateTrigger(run_date=run_date, timezone=tz),
        id=snooze_job_id,
        args=[user_id, direction],
        replace_existing=True
    )
    logger.info(f"Snoozed prompt for user {user_id} ({direction}) by {minutes} mins until {run_date}")


async def init_scheduler(bot, send_prompt_func):
    """
    Initializes and starts the scheduler, loading all existing users from SQLite.
    """
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started successfully.")

    users = database.get_all_users()
    for u in users:
        schedule_user_commute(bot, u["user_id"], send_prompt_func)

