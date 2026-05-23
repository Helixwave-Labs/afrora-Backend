import os
import stripe
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session, joinedload
from app import models, auth
from app.database import get_db
from pydantic import BaseModel

router = APIRouter(
    prefix="/payments",
    tags=["Payments"]
)

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# Simple inline schema for checkout requests
class CheckoutRequest(BaseModel):
    order_id: int
    success_url: str
    cancel_url: str

@router.post("/checkout-session", status_code=status.HTTP_200_OK)
def create_checkout_session(
    payload: CheckoutRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Creates a Stripe Checkout Session for a pending order.
    Returns the session URL for the frontend to redirect the customer.
    """
    if not stripe.api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stripe is not configured on this server."
        )

    # Fetch order and ensure it belongs to the current user
    order = db.query(models.Order).options(
        joinedload(models.Order.items).joinedload(models.OrderItem.product)
    ).filter(models.Order.id == payload.order_id).first()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")

    if order.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to pay for this order.")

    if order.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only pending orders can be paid for. Current status: {order.status}"
        )

    # Build Stripe line items
    line_items = []
    for item in order.items:
        product_name = item.product.name if item.product else "Deleted Product"
        line_items.append({
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": product_name,
                },
                "unit_amount": int(item.price * 100),  # Stripe expects amount in cents
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
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Handles Stripe webhooks. When payment is complete, marks the order as paid/processing.
    """
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
        # Invalid payload
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload.")
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature.")

    # Process checkout.session.completed event
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        order_id = session.get("metadata", {}).get("order_id")

        if order_id:
            order_id = int(order_id)
            order = db.query(models.Order).filter(models.Order.id == order_id).first()
            if order:
                # Progress status to 'processing' indicating payment was secured
                order.status = "processing"
                db.commit()

    return {"status": "success"}
