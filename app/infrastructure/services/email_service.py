import os
import secrets
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, errors, MessageType
from pydantic import EmailStr, SecretStr, NameEmail
from dotenv import load_dotenv

load_dotenv()

conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME", "default@example.com"),
    MAIL_PASSWORD=SecretStr(os.getenv("MAIL_PASSWORD", "defaultpassword")),
    MAIL_FROM=os.getenv("MAIL_FROM", "default@example.com"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),
    MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.example.com"),
    MAIL_STARTTLS=os.getenv("MAIL_STARTTLS", "True").lower() in ('true', '1', 't'),
    MAIL_SSL_TLS=os.getenv("MAIL_SSL_TLS", "False").lower() in ('true', '1', 't'),
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

def generate_otp(length: int = 6) -> str:
    return "".join([str(secrets.randbelow(10)) for _ in range(length)])

async def send_verification_email(email: EmailStr, otp: str):
    html = f"""
    <html>
        <body>
            <p>Hi,</p>
            <p>Thank you for registering with Afrovogue Commercial.</p>
            <p>Your One-Time Password (OTP) for email verification is: <strong>{otp}</strong></p>
            <p>This code will expire in 10 minutes.</p>
        </body>
    </html>
    """

    message = MessageSchema(
        subject="Afrovogue: Verify Your Email Address",
        recipients=[NameEmail(name="", email=str(email))],
        body=html,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    try:
        await fm.send_message(message)
    except errors.ConnectionErrors as e:
        print(f"Failed to send verification email: {e}")

async def send_password_reset_email(email: EmailStr, token: str):
    reset_link = f"http://your-frontend-domain.com/reset-password?token={token}"

    html = f"""
    <html>
        <body>
            <p>Hi,</p>
            <p>You requested a password reset. Click the link below to reset your password:</p>
            <p><a href="{reset_link}">{reset_link}</a></p>
            <p>This link will expire in 15 minutes.</p>
            <p>If you did not request a password reset, please ignore this email.</p>
        </body>
    </html>
    """

    message = MessageSchema(
        subject="Afrovogue: Password Reset Request",
        recipients=[NameEmail(name="", email=str(email))],
        body=html,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    try:
        await fm.send_message(message)
    except errors.ConnectionErrors as e:
        print(f"Failed to send password reset email: {e}")
