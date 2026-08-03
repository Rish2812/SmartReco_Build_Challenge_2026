"""
Bonus feature: scheduled proactive delivery. A daily background job re-checks every
active user's recommendation (reusing the same cache-first gate, so it doesn't spam
LLM calls for inactive users) and emails a digest if a fresh recommendation exists.

If SMTP settings are blank in .env, this logs the digest instead of sending — so the
scheduler is still demonstrable without real mail credentials configured.
"""
import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.database import SessionLocal
from app.models import User
from app.agent.service import get_or_refresh_recommendation

logger = logging.getLogger("smartreco.digest")


async def _send_email(to_email: str, subject: str, body: str) -> None:
    if not settings.smtp_host:
        logger.info("[DIGEST - no SMTP configured, logging instead] to=%s subject=%s\n%s", to_email, subject, body)
        return

    import aiosmtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = settings.digest_from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
        start_tls=True,
    )


async def run_daily_digest() -> None:
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.role == "user").all()
        for user in users:
            rec = get_or_refresh_recommendation(db, user.id)
            if not rec:
                continue
            subject = "Your personalized picks from SmartReco"
            body = f"Hi,\n\n{rec.narrative}\n\n— SmartReco"
            await _send_email(user.email, subject, body)
    finally:
        db.close()


def _job():
    asyncio.run(run_daily_digest())


def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_daily_digest,
        trigger="cron",
        hour=settings.digest_send_hour,
        minute=settings.digest_send_minute,
        id="daily_digest",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Daily digest scheduled for %02d:%02d server time.",
        settings.digest_send_hour,
        settings.digest_send_minute,
    )
    return scheduler
