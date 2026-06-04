from abc import ABC, abstractmethod
from typing import Optional
from app.domain.entities.escrow import EscrowDomainModel

class IEscrowRepository(ABC):
    @abstractmethod
    async def get_by_order_id(self, order_id: str) -> Optional[EscrowDomainModel]:
        pass

    @abstractmethod
    async def save(self, escrow: EscrowDomainModel) -> None:
        pass
