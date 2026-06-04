from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.infrastructure.models import models
from app.application.dtos import product as schemas
from app.infrastructure.services import auth
from app.infrastructure.database.database import get_db, get_read_db

router = APIRouter(
    prefix="/categories",
    tags=["Categories"]
)

def check_admin(current_user: models.User = Depends(auth.get_current_user)):
    """Dependency to check if the current user is an admin."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform this action."
        )

# --- Category Endpoints ---

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.CategoryOut, dependencies=[Depends(check_admin)])
async def create_category(category: schemas.CategoryCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Category).filter(models.Category.name == category.name))
    db_category = result.scalars().first()
    if db_category:
        raise HTTPException(status_code=400, detail="Category with this name already exists")
    new_category = models.Category(name=category.name)
    db.add(new_category)
    await db.commit()
    await db.refresh(new_category)
    return new_category

@router.get("/", response_model=List[schemas.CategoryOut])
async def get_all_categories(db: AsyncSession = Depends(get_read_db)):
    result = await db.execute(select(models.Category))
    categories = result.scalars().all()
    return categories

@router.put("/{category_id}", response_model=schemas.CategoryOut, dependencies=[Depends(check_admin)])
async def update_category(category_id: str, category_update: schemas.CategoryCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Category).filter(models.Category.id == category_id))
    db_category = result.scalars().first()
    if not db_category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    existing_result = await db.execute(select(models.Category).filter(models.Category.name == category_update.name, models.Category.id != category_id))
    existing_category = existing_result.scalars().first()
    if existing_category:
        raise HTTPException(status_code=400, detail="Category name already in use")

    db_category.name = category_update.name
    await db.commit()
    await db.refresh(db_category)
    return db_category

@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(check_admin)])
async def delete_category(category_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Category).filter(models.Category.id == category_id))
    db_category = result.scalars().first()
    if not db_category:
        raise HTTPException(status_code=404, detail="Category not found")
    await db.delete(db_category)
    await db.commit()
    return

# --- SubCategory Endpoints ---

@router.post("/{category_id}/subcategories", status_code=status.HTTP_201_CREATED, response_model=schemas.SubCategoryOut, dependencies=[Depends(check_admin)])
async def create_subcategory(category_id: str, subcategory: schemas.SubCategoryCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Category).filter(models.Category.id == category_id))
    db_category = result.scalars().first()
    if not db_category:
        raise HTTPException(status_code=404, detail="Parent category not found")
    
    new_subcategory = models.SubCategory(**subcategory.model_dump(), category_id=category_id)
    db.add(new_subcategory)
    await db.commit()
    await db.refresh(new_subcategory)
    return new_subcategory

@router.put("/subcategories/{subcategory_id}", response_model=schemas.SubCategoryOut, dependencies=[Depends(check_admin)])
async def update_subcategory(subcategory_id: str, subcategory_update: schemas.SubCategoryCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.SubCategory).filter(models.SubCategory.id == subcategory_id))
    db_subcategory = result.scalars().first()
    if not db_subcategory:
        raise HTTPException(status_code=404, detail="Subcategory not found")
    
    db_subcategory.name = subcategory_update.name
    await db.commit()
    await db.refresh(db_subcategory)
    return db_subcategory

@router.delete("/subcategories/{subcategory_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(check_admin)])
async def delete_subcategory(subcategory_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.SubCategory).filter(models.SubCategory.id == subcategory_id))
    db_subcategory = result.scalars().first()
    if not db_subcategory:
        raise HTTPException(status_code=404, detail="Subcategory not found")
    await db.delete(db_subcategory)
    await db.commit()
    return
