from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.domain.entities.escrow import EscrowDomainModel
from app.domain.repositories.escrow_repository import IEscrowRepository
from app.infrastructure.models import models

class SqlAlchemyEscrowRepository(IEscrowRepository):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_order_id(self, order_id: str) -> Optional[EscrowDomainModel]:
        stmt = select(models.Escrow).options(joinedload(models.Escrow.order)).filter(models.Escrow.order_id == order_id)
        result = await self.db.execute(stmt)
        db_escrow = result.scalars().first()
        if not db_escrow:
            return None

        # Map SQLAlchemy model to Pure Domain Model
        return EscrowDomainModel(
            id=db_escrow.id,
            order_id=db_escrow.order_id,
            amount=db_escrow.amount,
            status=db_escrow.status,
            created_at=db_escrow.created_at,
            inspection_ends_at=db_escrow.inspection_ends_at,
            released_at=db_escrow.released_at
        )

    async def save(self, escrow: EscrowDomainModel) -> None:
        stmt = select(models.Escrow).options(joinedload(models.Escrow.order)).filter(models.Escrow.id == escrow.id)
        result = await self.db.execute(stmt)
        db_escrow = result.scalars().first()

        if not db_escrow:
            db_escrow = models.Escrow(
                id=escrow.id,
                order_id=escrow.order_id,
                amount=escrow.amount,
                status=escrow.status,
                created_at=escrow.created_at,
                inspection_ends_at=escrow.inspection_ends_at,
                released_at=escrow.released_at
            )
            self.db.add(db_escrow)
        else:
            db_escrow.status = escrow.status
            db_escrow.released_at = escrow.released_at
            
            if escrow.status == "released" and db_escrow.order:
                db_escrow.order.status = "completed"
            elif escrow.status == "disputed" and db_escrow.order:
                db_escrow.order.status = "processing"
            elif escrow.status == "refunded" and db_escrow.order:
                db_escrow.order.status = "refunded"

        await self.db.flush()
