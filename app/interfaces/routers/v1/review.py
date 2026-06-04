from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from typing import List

from app.infrastructure.models import models
from app.application.dtos import product as schemas
from app.infrastructure.services import auth
from app.infrastructure.database.database import get_db, get_read_db

router = APIRouter(
    tags=["Reviews"]
)

@router.post("/products/{product_id}/reviews", status_code=status.HTTP_201_CREATED, response_model=schemas.ReviewOut)
async def create_review(
    product_id: str,
    review_data: schemas.ReviewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if not (1 <= review_data.rating <= 5):
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5.")

    prod_res = await db.execute(select(models.Product).filter(models.Product.id == product_id))
    product = prod_res.scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    new_review = models.Review(
        product_id=product_id,
        user_id=current_user.id,
        rating=review_data.rating,
        comment=review_data.comment
    )

    try:
        db.add(new_review)
        await db.commit()
        stmt = select(models.Review).options(joinedload(models.Review.user)).filter(models.Review.id == new_review.id)
        res = await db.execute(stmt)
        new_review = res.scalars().first()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="You have already reviewed this product.")

    return new_review

@router.get("/products/{product_id}/reviews", response_model=List[schemas.ReviewOut])
async def get_reviews_for_product(product_id: str, db: AsyncSession = Depends(get_read_db)):
    prod_res = await db.execute(select(models.Product).filter(models.Product.id == product_id))
    if not prod_res.scalars().first():
         raise HTTPException(status_code=404, detail="Product not found.")

    result = await db.execute(
        select(models.Review).options(joinedload(models.Review.user)).filter(models.Review.product_id == product_id)
    )
    reviews = result.scalars().all()
    return reviews

@router.put("/reviews/{review_id}", response_model=schemas.ReviewOut)
async def update_review(
    review_id: str,
    review_data: schemas.ReviewUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    result = await db.execute(
        select(models.Review).options(joinedload(models.Review.user)).filter(models.Review.id == review_id)
    )
    review = result.scalars().first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found.")

    if review.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to perform this action.")

    if not (1 <= review_data.rating <= 5):
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5.")

    review.rating = review_data.rating
    review.comment = review_data.comment
    await db.commit()
    await db.refresh(review)
    return review

@router.delete("/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(
    review_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    result = await db.execute(select(models.Review).filter(models.Review.id == review_id))
    review = result.scalars().first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found.")

    if review.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to perform this action.")

    await db.delete(review)
    await db.commit()
    return
