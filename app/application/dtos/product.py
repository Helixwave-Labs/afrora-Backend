from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from app.application.dtos.user import UserOut

# Schemas for Categories and SubCategories
class SubCategoryBase(BaseModel):
    name: str

class SubCategoryCreate(SubCategoryBase):
    pass

class SubCategoryOut(SubCategoryBase):
    id: str
    category_id: str
    class Config:
        from_attributes = True

class CategoryBase(BaseModel):
    name: str

class CategoryCreate(CategoryBase):
    pass

class CategoryOut(CategoryBase):
    id: str
    subcategories: list[SubCategoryOut] = []
    class Config:
        from_attributes = True

# Schemas for Products
class ProductBase(BaseModel):
    name: str
    description: str
    price: float

class ProductCreate(ProductBase):
    subcategory_id: str
    quantity: int

# Schemas for Reviews
class ReviewBase(BaseModel):
    rating: int
    comment: Optional[str] = None

class ReviewCreate(ReviewBase):
    pass

class ReviewUpdate(ReviewBase):
    pass

class ReviewOut(ReviewBase):
    id: str
    user: UserOut
    created_at: datetime
    class Config:
        from_attributes = True

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    subcategory_id: Optional[str] = None
    quantity: Optional[int] = None

class ProductOut(ProductBase):
    id: str
    image_url: Optional[str] = None
    owner_id: str
    quantity: int
    owner: UserOut # Nested schema to show owner details
    subcategory: SubCategoryOut
    reviews: list[ReviewOut] = []
    average_rating: Optional[float] = None
    review_count: int = 0

    class Config:
        from_attributes = True

class CartProductOut(BaseModel):
    """A simplified product schema for cart items."""
    id: str
    name: str
    price: float
    image_url: Optional[str] = None

    class Config:
        from_attributes = True

class ShopOut(BaseModel):
    id: str
    owner_id: str
    name: str
    description: Optional[str] = None
    banner_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class GlobalSearchOut(BaseModel):
    products: list[CartProductOut]
    shops: list[ShopOut]
