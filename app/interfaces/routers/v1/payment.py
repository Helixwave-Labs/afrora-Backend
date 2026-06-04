import os
import stripe
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy import select
from app.infrastructure.models import models
from app.infrastructure.services import auth
from app.infrastructure.database.database import get_db
from pydantic import BaseModel

router = APIRouter(
    prefix="/payments",
    tags=["Payments"]
)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

class CheckoutRequest(BaseModel):
    order_id: str
    success_url: str
    cancel_url: str

@router.post("/checkout-session", status_code=status.HTTP_200_OK)
async def create_checkout_session(
    payload: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if not stripe.api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stripe is not configured on this server."
        )

    result = await db.execute(
        select(models.Order).options(
            joinedload(models.Order.items).joinedload(models.OrderItem.product)
        ).filter(models.Order.id == payload.order_id)
    )
    order = result.scalars().unique().first()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")

    if order.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to pay for this order.")

    if order.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only pending orders can be paid for. Current status: {order.status}"
        )

    line_items = []
    for item in order.items:
        product_name = item.product.name if item.product else "Deleted Product"
        line_items.append({
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": product_name,
                },
                "unit_amount": int(item.price * 100),
            },
            "quantity": item.quantity,
        })

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=line_items,
            mode="payment",
            success_url=payload.success_url,
            cancel_url=payload.cancel_url,
            metadata={
                "order_id": order.id,
                "user_email": current_user.email
            }
        )
        return {"checkout_url": session.url}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stripe session creation failed: {str(e)}"
        )

@router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stripe Webhook Secret is not configured."
        )

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload.")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature.")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        order_id = session.get("metadata", {}).get("order_id")

        if order_id:
            result = await db.execute(select(models.Order).filter(models.Order.id == order_id))
            order = result.scalars().first()
            if order:
                from datetime import datetime, timedelta, timezone
                order.status = "processing"
                
                escrow_res = await db.execute(select(models.Escrow).filter(models.Escrow.order_id == order_id))
                existing_escrow = escrow_res.scalars().first()
                if not existing_escrow:
                    escrow = models.Escrow(
                        order_id=order.id,
                        amount=order.total_price,
                        status="held",
                        inspection_ends_at=datetime.now(timezone.utc) + timedelta(hours=48)
                    )
                    db.add(escrow)
                
                await db.commit()

    return {"status": "success"}
