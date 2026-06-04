from pydantic import BaseModel
from typing import List
from app.application.dtos.product import CartProductOut

class WishlistOut(BaseModel):
    products: list[CartProductOut]

class WishlistMergeRequest(BaseModel):
    product_ids: list[str]
