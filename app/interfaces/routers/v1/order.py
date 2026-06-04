from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy import select, delete
from typing import List, Optional

from app.infrastructure.models import models
from app.application.dtos import order as schemas
from app.infrastructure.services import auth
from app.infrastructure.database.database import get_db, get_read_db

router = APIRouter(
    prefix="/orders",
    tags=["Orders"]
)

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.OrderOut)
async def create_order_from_cart(
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shopping cart is empty.")

    product_ids = [item.product_id for item in cart.items]
    await db.execute(
        select(models.Product).filter(models.Product.id.in_(product_ids)).with_for_update()
    )

    for item in cart.items:
        await db.refresh(item.product)
        if item.product.quantity < item.quantity:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Not enough stock for {item.product.name}. Available: {item.product.quantity}, Requested: {item.quantity}")

    total_price = sum(item.product.price * item.quantity for item in cart.items)

    new_order = models.Order(
        user_id=current_user.id,
        total_price=total_price,
        status="pending"
    )
    db.add(new_order)
    await db.flush()

    for item in cart.items:
        order_item = models.OrderItem(
            order_id=new_order.id,
            product_id=item.product_id,
            quantity=item.quantity,
            price=item.product.price
        )
        db.add(order_item)
        item.product.quantity -= item.quantity

    await db.execute(delete(models.CartItem).filter(models.CartItem.cart_id == cart.id))
    await db.commit()
    await db.refresh(new_order)

    res = await db.execute(
        select(models.Order).options(
            joinedload(models.Order.items).joinedload(models.OrderItem.product)
        ).filter(models.Order.id == new_order.id)
    )
    order_with_details = res.scalars().unique().first()
    return order_with_details

@router.get("/", response_model=List[schemas.OrderListOut])
async def get_user_orders(
    db: AsyncSession = Depends(get_read_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    result = await db.execute(
        select(models.Order).filter(models.Order.user_id == current_user.id).order_by(models.Order.created_at.desc())
    )
    orders = result.scalars().all()
    return orders

@router.get("/{order_id}", response_model=schemas.OrderOut)
async def get_order_details(
    order_id: str,
    db: AsyncSession = Depends(get_read_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    result = await db.execute(
        select(models.Order).options(
            joinedload(models.Order.items).joinedload(models.OrderItem.product)
        ).filter(models.Order.id == order_id)
    )
    order: Optional[models.Order] = result.scalars().unique().first()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")

    if order.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this order.")

    return order

# Admin Endpoints

def check_admin(current_user: models.User = Depends(auth.get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform this action."
        )

@router.get("/all/", response_model=List[schemas.OrderListOut], dependencies=[Depends(check_admin)])
async def get_all_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
    db: AsyncSession = Depends(get_read_db)
):
    result = await db.execute(
        select(models.Order).order_by(models.Order.created_at.desc()).offset(skip).limit(limit)
    )
    orders = result.scalars().all()
    return orders

@router.patch("/{order_id}/status", response_model=schemas.OrderOut, dependencies=[Depends(check_admin)])
async def update_order_status(
    order_id: str,
    order_update: schemas.OrderUpdate,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(models.Order).filter(models.Order.id == order_id))
    order: Optional[models.Order] = result.scalars().first()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")

    order.status = order_update.status.value
    await db.commit()

    res = await db.execute(
        select(models.Order).options(
            joinedload(models.Order.items).joinedload(models.OrderItem.product)
        ).filter(models.Order.id == order_id)
    )
    updated_order = res.scalars().unique().first()
    return updated_order
