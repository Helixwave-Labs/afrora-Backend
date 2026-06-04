from datetime import datetime
from typing import Optional

class EscrowDomainModel:
    def __init__(
        self,
        id: str,
        order_id: str,
        amount: float,
        status: str,  # "held", "released", "refunded", "disputed"
        created_at: datetime,
        inspection_ends_at: Optional[datetime] = None,
        released_at: Optional[datetime] = None
    ):
        self.id = id
        self.order_id = order_id
        self.amount = amount
        self.status = status
        self.created_at = created_at
        self.inspection_ends_at = inspection_ends_at
        self.released_at = released_at

    def release(self, released_time: datetime) -> None:
        if self.status != "held":
            raise ValueError(f"Cannot release escrow in status: {self.status}")
        self.status = "released"
        self.released_at = released_time

    def dispute(self, current_time: datetime) -> None:
        if self.status != "held":
            raise ValueError("Disputes can only be opened for active, held escrows.")
        if self.inspection_ends_at and current_time > self.inspection_ends_at:
            raise ValueError("The 48-hour buyer inspection window has expired. Escrow cannot be disputed.")
        self.status = "disputed"
