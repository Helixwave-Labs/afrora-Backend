import os
import asyncio
from arq.connections import RedisSettings
from app.email_utils import send_verification_email, send_password_reset_email

async def send_verification_email_task(ctx, email: str, otp: str):
    """Worker task to send email verification OTP."""
    await send_verification_email(email, otp)

async def send_password_reset_email_task(ctx, email: str, token: str):
    """Worker task to send password reset link."""
    await send_password_reset_email(email, token)

class WorkerSettings:
    """Settings class for running the arq worker process."""
    functions = [send_verification_email_task, send_password_reset_email_task]
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://redis:6379"))
