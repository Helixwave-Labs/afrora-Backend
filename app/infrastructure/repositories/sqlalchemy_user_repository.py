from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.domain.entities.user import UserDomainModel
from app.domain.repositories.user_repository import IUserRepository
from app.infrastructure.models import models

class SqlAlchemyUserRepository(IUserRepository):
    def __init__(self, db: AsyncSession):
        self.db = db

    def _map_to_domain(self, db_user: models.User) -> UserDomainModel:
        return UserDomainModel(
            id=db_user.id,
            username=db_user.username,
            email=db_user.email,
            hashed_password=db_user.hashed_password,
            is_active=db_user.is_active,
            otp=db_user.otp,
            otp_expires_at=db_user.otp_expires_at,
            role=db_user.role,
            password_reset_token=db_user.password_reset_token,
            password_reset_token_expires_at=db_user.password_reset_token_expires_at,
            created_at=db_user.created_at,
            profile_picture_url=db_user.profile_picture_url,
            phone=db_user.phone,
            country=db_user.country
        )

    async def get_by_id(self, user_id: str) -> Optional[UserDomainModel]:
        stmt = select(models.User).filter(models.User.id == user_id)
        result = await self.db.execute(stmt)
        db_user = result.scalars().first()
        return self._map_to_domain(db_user) if db_user else None

    async def get_by_email(self, email: str) -> Optional[UserDomainModel]:
        stmt = select(models.User).filter(models.User.email == email)
        result = await self.db.execute(stmt)
        db_user = result.scalars().first()
        return self._map_to_domain(db_user) if db_user else None

    async def get_by_username(self, username: str) -> Optional[UserDomainModel]:
        stmt = select(models.User).filter(models.User.username == username)
        result = await self.db.execute(stmt)
        db_user = result.scalars().first()
        return self._map_to_domain(db_user) if db_user else None

    async def get_by_reset_token(self, token: str) -> Optional[UserDomainModel]:
        stmt = select(models.User).filter(models.User.password_reset_token == token)
        result = await self.db.execute(stmt)
        db_user = result.scalars().first()
        return self._map_to_domain(db_user) if db_user else None

    async def list_users(self, skip: int, limit: int) -> List[UserDomainModel]:
        stmt = select(models.User).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        db_users = result.scalars().all()
        return [self._map_to_domain(u) for u in db_users]

    async def save(self, user: UserDomainModel) -> None:
        stmt = select(models.User).filter(models.User.id == user.id)
        result = await self.db.execute(stmt)
        db_user = result.scalars().first()

        if not db_user:
            db_user = models.User(
                id=user.id,
                username=user.username,
                email=user.email,
                hashed_password=user.hashed_password,
                is_active=user.is_active,
                otp=user.otp,
                otp_expires_at=user.otp_expires_at,
                role=user.role,
                password_reset_token=user.password_reset_token,
                password_reset_token_expires_at=user.password_reset_token_expires_at,
                profile_picture_url=user.profile_picture_url,
                phone=user.phone,
                country=user.country
            )
            self.db.add(db_user)
        else:
            db_user.username = user.username
            db_user.email = user.email
            db_user.hashed_password = user.hashed_password
            db_user.is_active = user.is_active
            db_user.otp = user.otp
            db_user.otp_expires_at = user.otp_expires_at
            db_user.role = user.role
            db_user.password_reset_token = user.password_reset_token
            db_user.password_reset_token_expires_at = user.password_reset_token_expires_at
            db_user.profile_picture_url = user.profile_picture_url
            db_user.phone = user.phone
            db_user.country = user.country

        await self.db.flush()
