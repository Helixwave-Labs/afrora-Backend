from pydantic import BaseModel
from enum import Enum
from datetime import datetime
from typing import Optional, List
from app.application.dtos.product import CartProductOut

class OrderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class OrderUpdate(BaseModel):
    status: OrderStatus

class OrderItemOut(BaseModel):
    quantity: int
    price: float  # Price per item at time of purchase
    product: Optional[CartProductOut]  # Product can be null if it's deleted later

    class Config:
        from_attributes = True

class OrderOut(BaseModel):
    id: str
    status: OrderStatus
    total_price: float
    created_at: datetime
    items: List[OrderItemOut]

    class Config:
        from_attributes = True

class OrderListOut(BaseModel):
    id: str
    status: OrderStatus
    total_price: float
    created_at: datetime

    class Config:
        from_attributes = True

class EscrowOut(BaseModel):
    id: str
    order_id: str
    amount: float
    status: str
    created_at: datetime
    inspection_ends_at: Optional[datetime] = None
    released_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class DisputeCreate(BaseModel):
    reason: str

class DisputeOut(BaseModel):
    id: str
    escrow_id: str
    buyer_id: str
    reason: str
    status: str
    resolution_details: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class PayoutRequest(BaseModel):
    amount: float

class PayoutRecordOut(BaseModel):
    id: str
    shop_id: str
    amount: float
    status: str
    reference: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
