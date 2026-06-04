from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from app.domain.entities.user import UserDomainModel
from app.domain.repositories.user_repository import IUserRepository
from app.infrastructure.services.email_service import generate_otp
from app.infrastructure.services import auth

class UserSignupUseCase:
    def __init__(self, user_repo: IUserRepository):
        self.user_repo = user_repo

    async def execute(self, name: str, email: str, password: str) -> UserDomainModel:
        # Check existing
        existing_email = await self.user_repo.get_by_email(email)
        if existing_email:
            raise ValueError("Email already registered")

        existing_name = await self.user_repo.get_by_username(name)
        if existing_name:
            raise ValueError("Username already taken")

        # Hash password and generate OTP
        hashed_password = auth.hash_password(password)
        otp = generate_otp()
        otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        # Generate a clean prefixed ID
        user_id = f"usr_{uuid.uuid4().hex[:12]}"

        # Create pure Domain Model
        user = UserDomainModel(
            id=user_id,
            username=name,
            email=email,
            hashed_password=hashed_password,
            is_active=False,
            otp=otp,
            otp_expires_at=otp_expires_at,
            role="user"
        )

        await self.user_repo.save(user)
        return user

class VerifyEmailUseCase:
    def __init__(self, user_repo: IUserRepository):
        self.user_repo = user_repo

    async def execute(self, email: str, otp: str) -> None:
        user = await self.user_repo.get_by_email(email)
        if not user:
            raise KeyError("User not found.")
        
        if user.is_active:
            return

        # Delegate validation and state transition to domain entity
        if not user.verify_otp(otp, datetime.now(timezone.utc)):
            raise ValueError("Invalid or expired OTP.")

        user.activate()
        await self.user_repo.save(user)

class UserLoginUseCase:
    def __init__(self, user_repo: IUserRepository):
        self.user_repo = user_repo

    async def execute(self, email: str, password: str) -> UserDomainModel:
        user = await self.user_repo.get_by_email(email)
        if not user or not auth.verify_password(password, user.hashed_password):
            raise KeyError("AUTH_INVALID_CREDENTIALS")

        if not user.is_active:
            raise PermissionError("AUTH_NOT_VERIFIED")

        return user
