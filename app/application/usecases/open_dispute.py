from datetime import datetime, timezone
from app.domain.repositories.escrow_repository import IEscrowRepository

class OpenDisputeUseCase:
    def __init__(self, escrow_repo: IEscrowRepository):
        self.escrow_repo = escrow_repo

    async def execute(self, order_id: str, reason: str, buyer_id: str, db_session) -> None:
        """
        Orchestrates opening a buyer dispute for a held escrow.
        """
        escrow = await self.escrow_repo.get_by_order_id(order_id)
        if not escrow:
            raise ValueError("Escrow record not found for this order.")

        # Delegate dispute validation and status transitions to the domain model
        escrow.dispute(datetime.now(timezone.utc))
        
        # Persist changes
        await self.escrow_repo.save(escrow)

        # Calculate priority
        amount = escrow.amount
        priority = "low"
        if amount >= 500:
            priority = "high"
        elif amount >= 100:
            priority = "medium"

        # Create dispute record in database
        from app.infrastructure.models import models
        dispute = models.Dispute(
            escrow_id=escrow.id,
            buyer_id=buyer_id,
            reason=reason,
            status="open",
            priority=priority
        )
        db_session.add(dispute)
