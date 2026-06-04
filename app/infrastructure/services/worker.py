import os
import asyncio
from arq.connections import RedisSettings
from arq import cron
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from datetime import datetime, timezone

from app.infrastructure.services.email_service import send_verification_email, send_password_reset_email
from app.infrastructure.database.database import AsyncSessionLocalWrite
from app.infrastructure.models import models

async def send_verification_email_task(ctx, email: str, otp: str):
    """Worker task to send email verification OTP."""
    await send_verification_email(email, otp)

async def send_password_reset_email_task(ctx, email: str, token: str):
    """Worker task to send password reset link."""
    await send_password_reset_email(email, token)

async def auto_release_escrows(ctx):
    """
    Scheduled cron job to automatically release held escrows that have exceeded the 48-hour inspection window.
    """
    async with AsyncSessionLocalWrite() as db:
        res = await db.execute(
            select(models.Escrow)
            .options(joinedload(models.Escrow.order))
            .filter(models.Escrow.status == "held")
            .filter(models.Escrow.inspection_ends_at <= datetime.now(timezone.utc))
        )
        expired_escrows = res.scalars().all()
        
        for escrow in expired_escrows:
            escrow.status = "released"
            escrow.released_at = datetime.now(timezone.utc)
            if escrow.order:
                escrow.order.status = "completed"
            
        if expired_escrows:
            await db.commit()
            print(f"Auto-released {len(expired_escrows)} expired escrows.")

class WorkerSettings:
    """Settings class for running the arq worker process."""
    functions = [send_verification_email_task, send_password_reset_email_task, auto_release_escrows]
    cron_jobs = [
        cron(auto_release_escrows, second=0)  # Runs every minute at the 0th second
    ]
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://redis:6379"))
