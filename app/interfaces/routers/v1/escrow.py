from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy import select, func
from typing import List, Optional
from datetime import datetime, timezone

from app.infrastructure.models import models
from app.application.dtos import order as schemas
from app.infrastructure.services import auth
from app.infrastructure.database.database import get_db, get_read_db

router = APIRouter(
    prefix="/escrow",
    tags=["Escrow & Payouts"]
)

@router.get("/orders/{order_id}", response_model=schemas.EscrowOut)
async def get_order_escrow_details(
    order_id: str,
    db: AsyncSession = Depends(get_read_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    res = await db.execute(
        select(models.Escrow)
        .options(joinedload(models.Escrow.order))
        .filter(models.Escrow.order_id == order_id)
    )
    escrow = res.scalars().first()
    if not escrow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escrow record not found for this order.")

    is_admin = current_user.role == "admin"
    is_buyer = escrow.order.user_id == current_user.id
    
    is_seller = False
    if current_user.role == "seller":
        shop_res = await db.execute(select(models.Shop).filter(models.Shop.owner_id == current_user.id))
        shop = shop_res.scalars().first()
        if shop:
            item_res = await db.execute(
                select(models.OrderItem)
                .join(models.Product)
                .filter(models.OrderItem.order_id == order_id)
                .filter(models.Product.shop_id == shop.id)
            )
            if item_res.scalars().first():
                is_seller = True

    if not (is_admin or is_buyer or is_seller):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this escrow record.")

    return escrow

@router.post("/orders/{order_id}/confirm-delivery", response_model=schemas.EscrowOut)
async def confirm_delivery(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    res = await db.execute(
        select(models.Escrow)
        .options(joinedload(models.Escrow.order))
        .filter(models.Escrow.order_id == order_id)
    )
    escrow = res.scalars().first()
    if not escrow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escrow record not found for this order.")

    if escrow.order.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the buyer can confirm delivery of this order.")

    from app.infrastructure.repositories.sqlalchemy_escrow_repository import SqlAlchemyEscrowRepository
    from app.application.usecases.confirm_delivery import ConfirmDeliveryUseCase

    try:
        repo = SqlAlchemyEscrowRepository(db)
        use_case = ConfirmDeliveryUseCase(repo)
        await use_case.execute(order_id)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    res = await db.execute(
        select(models.Escrow)
        .options(joinedload(models.Escrow.order))
        .filter(models.Escrow.order_id == order_id)
    )
    updated_escrow = res.scalars().first()
    return updated_escrow

@router.post("/orders/{order_id}/dispute", response_model=schemas.DisputeOut)
async def open_dispute(
    order_id: str,
    payload: schemas.DisputeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    res = await db.execute(
        select(models.Escrow)
        .options(joinedload(models.Escrow.order))
        .filter(models.Escrow.order_id == order_id)
    )
    escrow = res.scalars().first()
    if not escrow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escrow record not found for this order.")

    if escrow.order.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the buyer can open a dispute.")

    from app.infrastructure.repositories.sqlalchemy_escrow_repository import SqlAlchemyEscrowRepository
    from app.application.usecases.open_dispute import OpenDisputeUseCase

    try:
        repo = SqlAlchemyEscrowRepository(db)
        use_case = OpenDisputeUseCase(repo)
        await use_case.execute(order_id, payload.reason, current_user.id, db)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    disp_res = await db.execute(
        select(models.Dispute).filter(models.Dispute.escrow_id == escrow.id)
    )
    dispute = disp_res.scalars().first()
    return dispute

@router.post("/disputes/{dispute_id}/resolve", response_model=schemas.DisputeOut)
async def resolve_dispute(
    dispute_id: str,
    resolution_details: str,
    action: str,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can resolve disputes.")

    res = await db.execute(
        select(models.Dispute)
        .options(joinedload(models.Dispute.escrow).joinedload(models.Escrow.order))
        .filter(models.Dispute.id == dispute_id)
    )
    dispute = res.scalars().first()
    if not dispute:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispute not found.")

    if dispute.status != "open":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Dispute is already resolved: {dispute.status}")

    if action not in ["release", "refund"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid resolution action. Must be 'release' or 'refund'.")

    dispute.status = "resolved"
    dispute.resolution_details = resolution_details

    if action == "release":
        dispute.escrow.status = "released"
        dispute.escrow.released_at = datetime.now(timezone.utc)
        dispute.escrow.order.status = "completed"
    else:
        dispute.escrow.status = "refunded"
        dispute.escrow.order.status = "refunded"

    await db.commit()
    await db.refresh(dispute)
    return dispute

@router.get("/vendor/balance")
async def get_vendor_balance(
    db: AsyncSession = Depends(get_read_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != "seller":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only sellers can access the vendor dashboard.")

    shop_res = await db.execute(select(models.Shop).filter(models.Shop.owner_id == current_user.id))
    shop = shop_res.scalars().first()
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor shop not found.")

    released_query = (
        select(func.sum(models.OrderItem.price * models.OrderItem.quantity))
        .join(models.Product, models.OrderItem.product_id == models.Product.id)
        .join(models.Order, models.OrderItem.order_id == models.Order.id)
        .join(models.Escrow, models.Order.id == models.Escrow.order_id)
        .filter(models.Product.shop_id == shop.id)
        .filter(models.Escrow.status == "released")
    )
    released_res = await db.execute(released_query)
    released_total = released_res.scalar() or 0.0

    held_query = (
        select(func.sum(models.OrderItem.price * models.OrderItem.quantity))
        .join(models.Product, models.OrderItem.product_id == models.Product.id)
        .join(models.Order, models.OrderItem.order_id == models.Order.id)
        .join(models.Escrow, models.Order.id == models.Escrow.order_id)
        .filter(models.Product.shop_id == shop.id)
        .filter(models.Escrow.status.in_(["held", "disputed"]))
    )
    held_res = await db.execute(held_query)
    held_total = held_res.scalar() or 0.0

    payout_query = (
        select(func.sum(models.PayoutRecord.amount))
        .filter(models.PayoutRecord.shop_id == shop.id)
        .filter(models.PayoutRecord.status == "completed")
    )
    payout_res = await db.execute(payout_query)
    payouts_total = payout_res.scalar() or 0.0

    available_balance = released_total - payouts_total

    payout_list_res = await db.execute(
        select(models.PayoutRecord)
        .filter(models.PayoutRecord.shop_id == shop.id)
        .order_by(models.PayoutRecord.created_at.desc())
    )
    payouts = payout_list_res.scalars().all()

    return {
        "shop_id": shop.id,
        "shop_name": shop.name,
        "available_balance": max(0.0, available_balance),
        "held_balance": held_total,
        "total_earned": released_total,
        "total_withdrawn": payouts_total,
        "payouts": payouts
    }

@router.post("/vendor/payout", response_model=schemas.PayoutRecordOut)
async def request_payout(
    payload: schemas.PayoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != "seller":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only sellers can request payouts.")

    shop_res = await db.execute(select(models.Shop).filter(models.Shop.owner_id == current_user.id))
    shop = shop_res.scalars().first()
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor shop not found.")

    if payload.amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payout amount must be a positive number.")

    released_query = (
        select(func.sum(models.OrderItem.price * models.OrderItem.quantity))
        .join(models.Product, models.OrderItem.product_id == models.Product.id)
        .join(models.Order, models.OrderItem.order_id == models.Order.id)
        .join(models.Escrow, models.Order.id == models.Escrow.order_id)
        .filter(models.Product.shop_id == shop.id)
        .filter(models.Escrow.status == "released")
    )
    released_res = await db.execute(released_query)
    released_total = released_res.scalar() or 0.0

    payout_query = (
        select(func.sum(models.PayoutRecord.amount))
        .filter(models.PayoutRecord.shop_id == shop.id)
        .filter(models.PayoutRecord.status == "completed")
    )
    payout_res = await db.execute(payout_query)
    payouts_total = payout_res.scalar() or 0.0

    available_balance = released_total - payouts_total

    if payload.amount > available_balance:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient balance. Available: {available_balance} GHS, Requested: {payload.amount} GHS"
        )

    import uuid
    payout = models.PayoutRecord(
        shop_id=shop.id,
        amount=payload.amount,
        status="pending",
        reference=f"wth_{uuid.uuid4().hex[:10]}"
    )
    db.add(payout)
    await db.commit()
    await db.refresh(payout)
    return payout
