from pydantic import BaseModel
from app.application.dtos.product import CartProductOut

class CartItemAdd(BaseModel):
    product_id: str
    quantity: int

class CartItemOut(BaseModel):
    quantity: int
    product: CartProductOut

    class Config:
        from_attributes = True

class CartOut(BaseModel):
    items: list[CartItemOut]
    total_price: float
    total_items: int

class CartMergeItem(BaseModel):
    product_id: str
    quantity: int

class CartMergeRequest(BaseModel):
    items: list[CartMergeItem]
