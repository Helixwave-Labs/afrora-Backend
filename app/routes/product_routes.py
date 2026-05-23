from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query, Request
from typing import List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
import shutil
import os
from pathlib import Path
from datetime import datetime

from app import models, schemas, auth
from app.database import get_db
from app.s3_utils import upload_file_to_s3, delete_file_from_s3
from app.cache_utils import get_cached_data, set_cached_data, delete_cache_pattern

async def invalidate_product_cache(request: Request, product_id: Optional[int] = None):
    """Utility to invalidate product cache on writes."""
    await delete_cache_pattern(request, "products:list:*")
    if product_id:
        await delete_cache_pattern(request, f"product:id_{product_id}")

router = APIRouter(
    prefix="/products",
    tags=["Products"]
)

# Define constants for product image paths
PRODUCT_IMAGES_DIR = Path("static/product_images")
PRODUCT_IMAGES_URL_PREFIX = "/static/product_images"

# Ensure the product images directory exists on startup
os.makedirs(PRODUCT_IMAGES_DIR, exist_ok=True)

def save_image(file: UploadFile, owner_id: int) -> str:
    """Saves an uploaded image to AWS S3 (if configured) or locally, and returns its URL."""
    bucket_name = os.getenv("AWS_STORAGE_BUCKET_NAME")
    if bucket_name:
        return upload_file_to_s3(file, folder="product_images")

    # Local fallback
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    filename = file.filename
    file_extension = Path(filename).suffix
    unique_filename = f"{owner_id}_{int(datetime.utcnow().timestamp())}{file_extension}"
    file_path = PRODUCT_IMAGES_DIR / unique_filename

    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        file.file.close()

    return f"{PRODUCT_IMAGES_URL_PREFIX}/{unique_filename}"

def delete_image(image_url: Optional[str]):
    """Deletes an image file from AWS S3 or the local server if it exists."""
    if not image_url:
        return
    
    bucket_name = os.getenv("AWS_STORAGE_BUCKET_NAME")
    if bucket_name:
        delete_file_from_s3(image_url)
        return

    try:
        # Construct local path from URL: "/static/product_images/file.jpg" -> "static/product_images/file.jpg"
        local_path = Path(image_url.lstrip('/'))
        if local_path.is_file():
            os.remove(local_path)
    except OSError:
        # Log this error in a real application
        pass

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.ProductOut)
async def create_product(
    request: Request,
    name: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    quantity: int = Form(...),
    subcategory_id: int = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Create a new product with an image. Must be authenticated.
    """
    # Verify subcategory exists
    db_subcategory = db.query(models.SubCategory).filter(models.SubCategory.id == subcategory_id).first()
    if not db_subcategory:
        raise HTTPException(status_code=404, detail="Subcategory not found")

    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Invalid file type. Only images are allowed.")

    image_url = save_image(image, current_user.id)

    new_product = models.Product(
        name=name,
        description=description,
        price=price,
        quantity=quantity,
        image_url=image_url,
        owner_id=current_user.id,
        subcategory_id=subcategory_id
    )
    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    # Invalidate Cache
    await invalidate_product_cache(request)

    return new_product

@router.get("/", response_model=List[schemas.ProductOut])
async def get_all_products(
    request: Request,
    db: Session = Depends(get_db),
    category_id: Optional[int] = Query(None, description="Filter by parent category ID"),
    subcategory_id: Optional[int] = Query(None, description="Filter by subcategory ID"),
    search: Optional[str] = Query(None, description="Search for products by name or description"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1)
):
    """
    Retrieve a list of all products. Publicly accessible.
    Supports pagination, searching, and filtering by category/subcategory.
    """
    # Try serving from Redis cache
    cache_key = f"products:list:cat_{category_id}:sub_{subcategory_id}:q_{search}:skip_{skip}:lim_{limit}"
    cached_products = await get_cached_data(request, cache_key)
    if cached_products is not None:
        return cached_products

    products_query = db.query(models.Product).options(
        joinedload(models.Product.owner),
        joinedload(models.Product.subcategory)
    )

    if category_id:
        # Join with SubCategory to filter by the parent category_id
        products_query = products_query.join(models.SubCategory).filter(models.SubCategory.category_id == category_id)

    if subcategory_id:
        products_query = products_query.filter(models.Product.subcategory_id == subcategory_id)

    if search:
        # Optimize with PostgreSQL Full-Text Search if database is postgresql
        if db.bind and "postgresql" in str(db.bind.url):
            ts_vector = func.to_tsvector('english', models.Product.name + ' ' + models.Product.description)
            ts_query = func.plainto_tsquery('english', search)
            products_query = products_query.filter(ts_vector.op('@@')(ts_query))
        else:
            search_term = f"%{search}%"
            products_query = products_query.filter(
                (models.Product.name.ilike(search_term)) | (models.Product.description.ilike(search_term))
            )

    products = products_query.offset(skip).limit(limit).all()

    # Serialize results to serialize safely for Redis
    serialized_products = [schemas.ProductOut.model_validate(p).model_dump(mode='json') for p in products]
    await set_cached_data(request, cache_key, serialized_products, expire_seconds=300)

    return products

@router.get("/{product_id}", response_model=schemas.ProductOut)
async def get_product(request: Request, product_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a single product by its ID. Publicly accessible.
    """
    # Try serving from Redis cache
    cache_key = f"product:id_{product_id}"
    cached_product = await get_cached_data(request, cache_key)
    if cached_product is not None:
        return cached_product

    # Use joinedload to eagerly load related owner and subcategory in a single query
    product = db.query(models.Product).options(
        joinedload(models.Product.owner), # Eagerly load the product's owner
        joinedload(models.Product.subcategory), # Eagerly load the product's subcategory
        joinedload(models.Product.reviews).joinedload(models.Review.user) # Eagerly load reviews and the user for each review
    ).filter(models.Product.id == product_id).first()

    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # Calculate average rating and count
    review_count = len(product.reviews)
    if review_count > 0:
        average_rating = sum(r.rating for r in product.reviews) / review_count
    else:
        average_rating = None

    response_data = schemas.ProductOut(**product.__dict__, average_rating=average_rating, review_count=review_count)
    
    # Store response in Redis cache (expire in 10 minutes)
    await set_cached_data(request, cache_key, response_data.model_dump(mode='json'), expire_seconds=600)

    return response_data

@router.put("/{product_id}", response_model=schemas.ProductOut)
async def update_product(
    product_id: int,
    request: Request,
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    price: Optional[float] = Form(None),
    quantity: Optional[int] = Form(None),
    subcategory_id: Optional[int] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Update a product's details. Only the owner can update their product.
    """
    product_query = db.query(models.Product).filter(models.Product.id == product_id)
    product = product_query.first()

    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    if product.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to perform this action")

    if subcategory_id:
        db_subcategory = db.query(models.SubCategory).filter(models.SubCategory.id == subcategory_id).first()
        if not db_subcategory:
            raise HTTPException(status_code=404, detail="Subcategory not found")

    # Update fields individually to avoid type issues
    if name is not None:
        product.name = name
    if description is not None:
        product.description = description
    if price is not None:
        product.price = price
    if quantity is not None:
        product.quantity = quantity
    if subcategory_id is not None:
        product.subcategory_id = subcategory_id

    if image:
        if not image.content_type or not image.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Invalid file type. Only images are allowed.")
        # Delete old image and save new one
        delete_image(product.image_url)
        product.image_url = save_image(image, current_user.id)

    db.commit()
    db.refresh(product)

    # Invalidate Cache
    await invalidate_product_cache(request, product_id)

    return product

@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Delete a product. Only the owner or an admin can delete a product.
    """
    product = db.query(models.Product).filter(models.Product.id == product_id).first()

    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    if product.owner_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to perform this action")

    # Delete the associated image file first
    delete_image(product.image_url)

    db.delete(product)
    db.commit()

    # Invalidate Cache
    await invalidate_product_cache(request, product_id)

    return