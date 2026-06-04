from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.infrastructure.models import models
from app.application.dtos import product as schemas
from app.infrastructure.database.database import get_read_db

router = APIRouter(
    tags=["Search"]
)

@router.get("/search", response_model=schemas.GlobalSearchOut)
async def global_search(
    q: str = Query(..., description="Query term to search across products and shops"),
    db: AsyncSession = Depends(get_read_db)
):
    search_term = f"%{q}%"

    # Query products
    products_stmt = select(models.Product).filter(
        (models.Product.name.ilike(search_term)) | 
        (models.Product.description.ilike(search_term))
    ).limit(50)
    products_res = await db.execute(products_stmt)
    products = products_res.scalars().all()

    # Query shops
    shops_stmt = select(models.Shop).filter(
        (models.Shop.name.ilike(search_term)) | 
        (models.Shop.description.ilike(search_term))
    ).limit(50)
    shops_res = await db.execute(shops_stmt)
    shops = shops_res.scalars().all()

    return {
        "products": products,
        "shops": shops
    }
