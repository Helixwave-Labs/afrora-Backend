from datetime import datetime, timezone
from app.domain.repositories.escrow_repository import IEscrowRepository

class ConfirmDeliveryUseCase:
    def __init__(self, escrow_repo: IEscrowRepository):
        self.escrow_repo = escrow_repo

    async def execute(self, order_id: str) -> None:
        """
        Orchestrates delivery confirmation and releases held escrow funds.
        """
        escrow = await self.escrow_repo.get_by_order_id(order_id)
        if not escrow:
            raise ValueError("Escrow record not found for this order.")

        # Delegate execution of the domain rules to the domain model
        escrow.release(datetime.now(timezone.utc))
        
        # Persist the changed domain model state
        await self.escrow_repo.save(escrow)
