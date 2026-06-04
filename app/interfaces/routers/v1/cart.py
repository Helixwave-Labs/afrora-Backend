from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy import select
from typing import List

from app.infrastructure.models import models
from app.application.dtos import cart as schemas
from app.infrastructure.services import auth
from app.infrastructure.database.database import get_db

router = APIRouter(
    prefix="/cart",
    tags=["Shopping Cart"]
)

async def get_or_create_cart(db: AsyncSession, user_id: str) -> models.Cart:
    result = await db.execute(select(models.Cart).filter(models.Cart.user_id == user_id))
    cart = result.scalars().first()
    if not cart:
        cart = models.Cart(user_id=user_id)
        db.add(cart)
        await db.commit()
        await db.refresh(cart)
    return cart

@router.get("/", response_model=schemas.CartOut)
async def get_user_cart(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    result = await db.execute(
        select(models.Cart).options(
            joinedload(models.Cart.items).joinedload(models.CartItem.product)
        ).filter(models.Cart.user_id == current_user.id)
    )
    cart = result.scalars().unique().first()

    if not cart or not cart.items:
        return {"items": [], "total_price": 0.0, "total_items": 0}

    total_price = sum(item.product.price * item.quantity for item in cart.items)
    total_items = sum(item.quantity for item in cart.items)

    return {"items": cart.items, "total_price": total_price, "total_items": total_items}

@router.post("/items", response_model=schemas.CartOut)
async def add_item_to_cart(
    item_data: schemas.CartItemAdd,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if item_data.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be a positive integer.")

    cart = await get_or_create_cart(db, current_user.id)

    prod_res = await db.execute(select(models.Product).filter(models.Product.id == item_data.product_id))
    product = prod_res.scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    item_res = await db.execute(
        select(models.CartItem).filter(
            models.CartItem.cart_id == cart.id,
            models.CartItem.product_id == item_data.product_id
        )
    )
    cart_item = item_res.scalars().first()

    if cart_item:
        cart_item.quantity = item_data.quantity
    else:
        cart_item = models.CartItem(
            cart_id=cart.id,
            product_id=item_data.product_id,
            quantity=item_data.quantity
        )
        db.add(cart_item)

    await db.commit()
    return await get_user_cart(db, current_user)

@router.delete("/items/{product_id}", response_model=schemas.CartOut)
async def remove_item_from_cart(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    result = await db.execute(select(models.Cart).filter(models.Cart.user_id == current_user.id))
    cart = result.scalars().first()
    if not cart:
        raise HTTPException(status_code=404, detail="Cart not found.")

    item_res = await db.execute(
        select(models.CartItem).filter(
            models.CartItem.cart_id == cart.id,
            models.CartItem.product_id == product_id
        )
    )
    cart_item = item_res.scalars().first()

    if not cart_item:
        raise HTTPException(status_code=404, detail="Item not found in cart.")

    await db.delete(cart_item)
    await db.commit()
    return await get_user_cart(db, current_user)

@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def clear_cart(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    result = await db.execute(select(models.Cart).filter(models.Cart.user_id == current_user.id))
    cart = result.scalars().first()
    if cart:
        from sqlalchemy import delete
        await db.execute(delete(models.CartItem).filter(models.CartItem.cart_id == cart.id))
        await db.commit()
    return

@router.post("/merge", response_model=schemas.CartOut)
async def merge_cart(
    payload: schemas.CartMergeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    cart = await get_or_create_cart(db, current_user.id)

    for item in payload.items:
        if item.quantity <= 0:
            continue
        
        prod_res = await db.execute(select(models.Product).filter(models.Product.id == item.product_id))
        product = prod_res.scalars().first()
        if not product:
            continue
        
        item_res = await db.execute(
            select(models.CartItem).filter(
                models.CartItem.cart_id == cart.id,
                models.CartItem.product_id == item.product_id
            )
        )
        cart_item = item_res.scalars().first()

        if cart_item:
            cart_item.quantity += item.quantity
        else:
            cart_item = models.CartItem(
                cart_id=cart.id,
                product_id=item.product_id,
                quantity=item.quantity
            )
            db.add(cart_item)

    await db.commit()
    return await get_user_cart(db, current_user)
