from abc import ABC, abstractmethod
from typing import Optional, List
from app.domain.entities.user import UserDomainModel

class IUserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: str) -> Optional[UserDomainModel]:
        pass

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[UserDomainModel]:
        pass

    @abstractmethod
    async def get_by_username(self, username: str) -> Optional[UserDomainModel]:
        pass

    @abstractmethod
    async def get_by_reset_token(self, token: str) -> Optional[UserDomainModel]:
        pass

    @abstractmethod
    async def list_users(self, skip: int, limit: int) -> List[UserDomainModel]:
        pass

    @abstractmethod
    async def save(self, user: UserDomainModel) -> None:
        pass
