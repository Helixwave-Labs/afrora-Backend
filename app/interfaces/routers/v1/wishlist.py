from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from typing import List

from app.infrastructure.models import models
from app.application.dtos import wishlist as schemas
from app.infrastructure.services import auth
from app.infrastructure.database.database import get_db, get_read_db

router = APIRouter(
    prefix="/wishlist",
    tags=["Wishlist"]
)

@router.post("/products/{product_id}", status_code=status.HTTP_201_CREATED, response_model=schemas.CartProductOut)
async def add_to_wishlist(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    result = await db.execute(select(models.Product).filter(models.Product.id == product_id))
    product = result.scalars().first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")

    wishlist_item = models.WishlistItem(user_id=current_user.id, product_id=product_id)

    try:
        db.add(wishlist_item)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product already in wishlist.")

    return product

@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_wishlist(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    result = await db.execute(
        select(models.WishlistItem).filter(
            models.WishlistItem.user_id == current_user.id,
            models.WishlistItem.product_id == product_id
        )
    )
    wishlist_item = result.scalars().first()

    if not wishlist_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found in wishlist.")

    await db.delete(wishlist_item)
    await db.commit()
    return

@router.get("/", response_model=schemas.WishlistOut)
async def get_wishlist(
    db: AsyncSession = Depends(get_read_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    result = await db.execute(
        select(models.WishlistItem).options(
            joinedload(models.WishlistItem.product)
        ).filter(models.WishlistItem.user_id == current_user.id)
    )
    wishlist_items = result.scalars().all()
    products = [item.product for item in wishlist_items]
    return {"products": products}

@router.post("/merge", response_model=schemas.WishlistOut)
async def merge_wishlist(
    payload: schemas.WishlistMergeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    for product_id in payload.product_ids:
        prod_res = await db.execute(select(models.Product).filter(models.Product.id == product_id))
        product = prod_res.scalars().first()
        if not product:
            continue

        item_res = await db.execute(
            select(models.WishlistItem).filter(
                models.WishlistItem.user_id == current_user.id,
                models.WishlistItem.product_id == product_id
            )
        )
        wishlist_item = item_res.scalars().first()

        if not wishlist_item:
            wishlist_item = models.WishlistItem(user_id=current_user.id, product_id=product_id)
            db.add(wishlist_item)

    await db.commit()
    return await get_wishlist(db, current_user)
