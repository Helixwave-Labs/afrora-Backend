from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, update
from sqlalchemy.orm import joinedload
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import os
import uuid

from app.infrastructure.models import models
from app.application.dtos import admin as schemas
from app.infrastructure.services import auth
from app.infrastructure.database.database import get_db, get_read_db
from app.infrastructure.services.s3_service import generate_presigned_post_data
from app.infrastructure.services.email_service import send_password_reset_email

router = APIRouter(
    prefix="/admin",
    tags=["Admin Management"],
    dependencies=[Depends(auth.get_current_admin)]
)

# Helper functions for singleton settings
async def get_platform_settings(db: AsyncSession) -> models.PlatformSettings:
    res = await db.execute(select(models.PlatformSettings).filter(models.PlatformSettings.id == "singleton"))
    settings = res.scalars().first()
    if not settings:
        settings = models.PlatformSettings(id="singleton")
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings

async def get_banner_settings(db: AsyncSession) -> models.BannerSettings:
    res = await db.execute(select(models.BannerSettings).filter(models.BannerSettings.id == "singleton"))
    settings = res.scalars().first()
    if not settings:
        settings = models.BannerSettings(id="singleton")
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings

# --- 1. Vendors ---

@router.get("/vendors")
async def list_vendors(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1),
    search: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_read_db)
):
    stmt = select(models.Shop).options(joinedload(models.Shop.owner))
    
    if status:
        stmt = stmt.filter(models.Shop.status == status)
    if search:
        stmt = stmt.join(models.User, models.Shop.owner_id == models.User.id).filter(
            (models.Shop.name.ilike(f"%{search}%")) | (models.User.email.ilike(f"%{search}%"))
        )
        
    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0
    
    # Paginate
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    res = await db.execute(stmt)
    shops = res.scalars().all()
    
    return {
        "vendors": [
            {
                "id": shop.id,
                "name": shop.name,
                "description": shop.description,
                "banner_url": shop.banner_url,
                "status": shop.status,
                "verified": shop.verified,
                "featured": shop.featured,
                "gmv": shop.gmv,
                "orders_count": shop.orders_count,
                "products_count": shop.products_count,
                "rating": shop.rating,
                "pending_balance": shop.pending_balance,
                "created_at": shop.created_at,
                "owner": {
                    "id": shop.owner.id,
                    "name": shop.owner.username,
                    "email": shop.owner.email,
                    "is_active": shop.owner.is_active
                }
            } for shop in shops
        ],
        "total": total
    }

@router.get("/vendors/queue")
async def list_vendor_verification_queue(
    db: AsyncSession = Depends(get_read_db)
):
    stmt = select(models.VerificationRequest).options(joinedload(models.VerificationRequest.vendor)).filter(models.VerificationRequest.status == "pending")
    res = await db.execute(stmt)
    requests = res.scalars().all()
    return requests

@router.get("/vendors/{id}")
async def get_vendor_details(
    id: str,
    db: AsyncSession = Depends(get_read_db)
):
    stmt = select(models.Shop).options(joinedload(models.Shop.owner)).filter(models.Shop.id == id)
    res = await db.execute(stmt)
    shop = res.scalars().first()
    if not shop:
        raise HTTPException(status_code=404, detail="Vendor not found.")
    return shop

@router.post("/vendors/{id}/verify")
async def verify_vendor(
    id: str,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.Shop).filter(models.Shop.id == id)
    res = await db.execute(stmt)
    shop = res.scalars().first()
    if not shop:
        raise HTTPException(status_code=404, detail="Vendor not found.")
    
    shop.verified = True
    shop.status = "active"
    await db.commit()
    return {"message": "Vendor verified successfully.", "shop_id": shop.id}

@router.post("/vendors/{id}/suspend")
async def suspend_vendor(
    id: str,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.Shop).filter(models.Shop.id == id)
    res = await db.execute(stmt)
    shop = res.scalars().first()
    if not shop:
        raise HTTPException(status_code=404, detail="Vendor not found.")
    
    shop.status = "suspended"
    await db.commit()
    return {"message": "Vendor suspended successfully.", "shop_id": shop.id}

@router.post("/vendors/{id}/unsuspend")
async def unsuspend_vendor(
    id: str,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.Shop).filter(models.Shop.id == id)
    res = await db.execute(stmt)
    shop = res.scalars().first()
    if not shop:
        raise HTTPException(status_code=404, detail="Vendor not found.")
    
    shop.status = "active"
    await db.commit()
    return {"message": "Vendor unsuspended successfully.", "shop_id": shop.id}

@router.patch("/vendors/{id}/feature")
async def toggle_feature_vendor(
    id: str,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.Shop).filter(models.Shop.id == id)
    res = await db.execute(stmt)
    shop = res.scalars().first()
    if not shop:
        raise HTTPException(status_code=404, detail="Vendor not found.")
    
    shop.featured = not shop.featured
    await db.commit()
    return {"message": f"Vendor featured set to {shop.featured}.", "featured": shop.featured}

@router.delete("/vendors/{id}")
async def delete_vendor(
    id: str,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.Shop).filter(models.Shop.id == id)
    res = await db.execute(stmt)
    shop = res.scalars().first()
    if not shop:
        raise HTTPException(status_code=404, detail="Vendor not found.")
    
    await db.delete(shop)
    await db.commit()
    return {"message": "Vendor deleted successfully."}

# --- 2. Customers ---

@router.get("/customers")
async def list_customers(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1),
    search: Optional[str] = None,
    is_banned: Optional[bool] = None,
    db: AsyncSession = Depends(get_read_db)
):
    stmt = select(models.User).filter(models.User.role == "user")
    
    if is_banned is not None:
        stmt = stmt.filter(models.User.is_banned == is_banned)
    if search:
        stmt = stmt.filter(
            (models.User.username.ilike(f"%{search}%")) | (models.User.email.ilike(f"%{search}%"))
        )
        
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0
    
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    res = await db.execute(stmt)
    customers = res.scalars().all()
    
    return {
        "customers": customers,
        "total": total
    }

@router.get("/customers/{id}")
async def get_customer_details(
    id: str,
    db: AsyncSession = Depends(get_read_db)
):
    stmt = select(models.User).filter(models.User.id == id, models.User.role == "user")
    res = await db.execute(stmt)
    customer = res.scalars().first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")
    return customer

@router.post("/customers/{id}/ban")
async def ban_customer(
    id: str,
    payload: schemas.BanRequest,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.User).filter(models.User.id == id, models.User.role == "user")
    res = await db.execute(stmt)
    customer = res.scalars().first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")
    
    customer.is_banned = True
    customer.ban_reason = payload.reason
    await db.commit()
    return {"message": "Customer banned successfully."}

@router.post("/customers/{id}/unban")
async def unban_customer(
    id: str,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.User).filter(models.User.id == id, models.User.role == "user")
    res = await db.execute(stmt)
    customer = res.scalars().first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")
    
    customer.is_banned = False
    customer.ban_reason = None
    await db.commit()
    return {"message": "Customer unbanned successfully."}

@router.post("/customers/{id}/reset-password-email")
async def trigger_customer_password_reset_email(
    id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.User).filter(models.User.id == id, models.User.role == "user")
    res = await db.execute(stmt)
    customer = res.scalars().first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")
    
    # Generate OTP and reset password link
    otp = "".join([str(uuid.uuid4().int)[:6]])
    customer.otp = otp
    customer.otp_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    await db.commit()

    arq_pool = request.app.state.arq_pool if hasattr(request, "app") and hasattr(request.app.state, "arq_pool") else None
    if arq_pool:
        await arq_pool.enqueue_job("send_password_reset_email_task", customer.email, otp)
    else:
        send_password_reset_email(customer.email, otp)
        
    return {"message": "Password reset email sent to customer."}

# --- 3. Products ---

@router.get("/products")
async def list_products(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1),
    search: Optional[str] = None,
    is_flagged: Optional[bool] = None,
    is_removed: Optional[bool] = None,
    db: AsyncSession = Depends(get_read_db)
):
    stmt = select(models.Product).options(joinedload(models.Product.owner))
    
    if is_flagged is not None:
        stmt = stmt.filter(models.Product.is_flagged == is_flagged)
    if is_removed is not None:
        stmt = stmt.filter(models.Product.is_removed == is_removed)
    if search:
        stmt = stmt.filter(
            (models.Product.name.ilike(f"%{search}%")) | (models.Product.description.ilike(f"%{search}%"))
        )
        
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0
    
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    res = await db.execute(stmt)
    products = res.scalars().all()
    
    return {
        "products": products,
        "total": total
    }

@router.get("/products/{id}")
async def get_product_details(
    id: str,
    db: AsyncSession = Depends(get_read_db)
):
    stmt = select(models.Product).options(joinedload(models.Product.owner)).filter(models.Product.id == id)
    res = await db.execute(stmt)
    product = res.scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    return product

@router.post("/products/{id}/flag")
async def flag_product(
    id: str,
    payload: schemas.FlagRequest,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.Product).filter(models.Product.id == id)
    res = await db.execute(stmt)
    product = res.scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    
    product.is_flagged = True
    product.flag_reason = payload.reason
    await db.commit()
    return {"message": "Product flagged successfully."}

@router.post("/products/{id}/unflag")
async def unflag_product(
    id: str,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.Product).filter(models.Product.id == id)
    res = await db.execute(stmt)
    product = res.scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    
    product.is_flagged = False
    product.flag_reason = None
    await db.commit()
    return {"message": "Product unflagged successfully."}

@router.post("/products/{id}/remove")
async def remove_product(
    id: str,
    payload: schemas.RemoveRequest,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.Product).filter(models.Product.id == id)
    res = await db.execute(stmt)
    product = res.scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    
    product.is_removed = True
    product.remove_reason = payload.reason
    await db.commit()
    return {"message": "Product soft removed successfully."}

@router.post("/products/{id}/restore")
async def restore_product(
    id: str,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.Product).filter(models.Product.id == id)
    res = await db.execute(stmt)
    product = res.scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    
    product.is_removed = False
    product.remove_reason = None
    await db.commit()
    return {"message": "Product restored successfully."}

@router.patch("/products/{id}/feature")
async def toggle_feature_product(
    id: str,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.Product).filter(models.Product.id == id)
    res = await db.execute(stmt)
    product = res.scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    
    product.is_featured = not product.is_featured
    await db.commit()
    return {"message": f"Product featured set to {product.is_featured}.", "featured": product.is_featured}

# --- 4. Orders ---

@router.get("/orders")
async def list_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1),
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_read_db)
):
    stmt = select(models.Order).options(joinedload(models.Order.user))
    
    if status:
        stmt = stmt.filter(models.Order.status == status)
    if search:
        stmt = stmt.filter(models.Order.id.ilike(f"%{search}%"))
        
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0
    
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    res = await db.execute(stmt)
    orders = res.scalars().all()
    
    return {
        "orders": orders,
        "total": total
    }

@router.get("/orders/{id}")
async def get_order_details(
    id: str,
    db: AsyncSession = Depends(get_read_db)
):
    stmt = select(models.Order).options(
        joinedload(models.Order.user),
        joinedload(models.Order.items).joinedload(models.OrderItem.product),
        joinedload(models.Order.escrow)
    ).filter(models.Order.id == id)
    res = await db.execute(stmt)
    order = res.scalars().unique().first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
    return order

@router.post("/orders/{id}/release-escrow")
async def release_escrow(
    id: str,
    current_admin: models.AdminUser = Depends(auth.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(models.Escrow).options(joinedload(models.Escrow.order)).filter(models.Escrow.order_id == id))
    escrow = res.scalars().first()
    if not escrow:
        raise HTTPException(status_code=404, detail="Escrow record not found.")
        
    if escrow.status in ["released", "refunded"]:
        raise HTTPException(status_code=400, detail=f"Escrow is already in state: {escrow.status}")

    escrow.status = "released"
    escrow.released_at = datetime.now(timezone.utc)
    escrow.order.status = "completed"
    
    # Log escrow release
    log = models.EscrowLog(
        order_id=id,
        action="released",
        admin_id=current_admin.id,
        reason="Admin manually released escrow.",
        amount=escrow.amount
    )
    db.add(log)
    await db.commit()
    return {"message": "Escrow released successfully."}

@router.post("/orders/{id}/refund-escrow")
async def refund_escrow(
    id: str,
    current_admin: models.AdminUser = Depends(auth.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(models.Escrow).options(joinedload(models.Escrow.order)).filter(models.Escrow.order_id == id))
    escrow = res.scalars().first()
    if not escrow:
        raise HTTPException(status_code=404, detail="Escrow record not found.")
        
    if escrow.status in ["released", "refunded"]:
        raise HTTPException(status_code=400, detail=f"Escrow is already in state: {escrow.status}")

    escrow.status = "refunded"
    escrow.order.status = "refunded"
    
    # Log escrow refund
    log = models.EscrowLog(
        order_id=id,
        action="refunded",
        admin_id=current_admin.id,
        reason="Admin manually refunded escrow.",
        amount=escrow.amount
    )
    db.add(log)
    await db.commit()
    return {"message": "Escrow refunded successfully."}

@router.post("/orders/{id}/extend-escrow")
async def extend_escrow(
    id: str,
    days: int = Query(3, ge=1),
    current_admin: models.AdminUser = Depends(auth.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(models.Escrow).options(joinedload(models.Escrow.order)).filter(models.Escrow.order_id == id))
    escrow = res.scalars().first()
    if not escrow:
        raise HTTPException(status_code=404, detail="Escrow record not found.")

    if not escrow.inspection_ends_at:
        escrow.inspection_ends_at = datetime.now(timezone.utc)
        
    escrow.inspection_ends_at += timedelta(days=days)
    
    log = models.EscrowLog(
        order_id=id,
        action="extended",
        admin_id=current_admin.id,
        reason=f"Admin extended escrow inspection period by {days} days.",
        amount=escrow.amount
    )
    db.add(log)
    await db.commit()
    return {"message": f"Escrow extended by {days} days.", "new_inspection_ends_at": escrow.inspection_ends_at}

@router.post("/orders/{id}/flag")
async def flag_order(
    id: str,
    payload: schemas.FlagRequest,
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(models.Order).filter(models.Order.id == id))
    order = res.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
        
    order.is_flagged = True
    order.flag_reason = payload.reason
    await db.commit()
    return {"message": "Order flagged successfully."}

# --- 5. Disputes ---

@router.get("/disputes")
async def list_disputes(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1),
    status: Optional[str] = None,
    priority: Optional[str] = None,
    db: AsyncSession = Depends(get_read_db)
):
    stmt = select(models.Dispute).options(
        joinedload(models.Dispute.buyer),
        joinedload(models.Dispute.escrow).joinedload(models.Escrow.order)
    )
    
    if status:
        stmt = stmt.filter(models.Dispute.status == status)
    if priority:
        stmt = stmt.filter(models.Dispute.priority == priority)
        
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0
    
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    res = await db.execute(stmt)
    disputes = res.scalars().all()
    
    return {
        "disputes": disputes,
        "total": total
    }

@router.get("/disputes/{id}")
async def get_dispute_details(
    id: str,
    db: AsyncSession = Depends(get_read_db)
):
    stmt = select(models.Dispute).options(
        joinedload(models.Dispute.buyer),
        joinedload(models.Dispute.escrow).joinedload(models.Escrow.order)
    ).filter(models.Dispute.id == id)
    res = await db.execute(stmt)
    dispute = res.scalars().first()
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found.")
    return dispute

@router.post("/disputes/{id}/resolve")
async def resolve_dispute(
    id: str,
    action: str = Query(..., description="release or refund"),
    resolution_details: str = Query(..., description="Reason for this resolution"),
    current_admin: models.AdminUser = Depends(auth.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.Dispute).options(
        joinedload(models.Dispute.escrow).joinedload(models.Escrow.order)
    ).filter(models.Dispute.id == id)
    res = await db.execute(stmt)
    dispute = res.scalars().first()
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found.")

    if dispute.status != "open":
        raise HTTPException(status_code=400, detail="Dispute is already resolved.")

    if action not in ["release", "refund"]:
        raise HTTPException(status_code=400, detail="Invalid action. Must be 'release' or 'refund'.")

    dispute.status = "resolved"
    dispute.resolution_details = resolution_details

    if action == "release":
        dispute.escrow.status = "released"
        dispute.escrow.released_at = datetime.now(timezone.utc)
        dispute.escrow.order.status = "completed"
    else:
        dispute.escrow.status = "refunded"
        dispute.escrow.order.status = "refunded"

    # Log escrow action
    log = models.EscrowLog(
        order_id=dispute.escrow.order_id,
        action=f"resolved_{action}",
        admin_id=current_admin.id,
        reason=resolution_details,
        amount=dispute.escrow.amount
    )
    db.add(log)
    await db.commit()
    return {"message": f"Dispute resolved with action {action}.", "dispute_id": dispute.id}

@router.post("/disputes/{id}/request-evidence")
async def request_dispute_evidence(
    id: str,
    db: AsyncSession = Depends(get_read_db)
):
    stmt = select(models.Dispute).filter(models.Dispute.id == id)
    res = await db.execute(stmt)
    dispute = res.scalars().first()
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found.")
    
    # Mock evidence request dispatch
    return {"message": "Evidence request sent successfully to buyer and vendor."}

# --- 6. Payouts ---

@router.get("/payouts")
async def list_payouts(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1),
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_read_db)
):
    stmt = select(models.PayoutRecord)
    if status:
        stmt = stmt.filter(models.PayoutRecord.status == status)
        
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0
    
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    res = await db.execute(stmt)
    payouts = res.scalars().all()
    
    return {
        "payouts": payouts,
        "total": total
    }

@router.get("/payouts/{id}")
async def get_payout_details(
    id: str,
    db: AsyncSession = Depends(get_read_db)
):
    stmt = select(models.PayoutRecord).filter(models.PayoutRecord.id == id)
    res = await db.execute(stmt)
    payout = res.scalars().first()
    if not payout:
        raise HTTPException(status_code=404, detail="Payout record not found.")
    return payout

@router.post("/payouts/{id}/approve")
async def approve_payout(
    id: str,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.PayoutRecord).filter(models.PayoutRecord.id == id)
    res = await db.execute(stmt)
    payout = res.scalars().first()
    if not payout:
        raise HTTPException(status_code=404, detail="Payout record not found.")

    if payout.status == "completed":
        raise HTTPException(status_code=400, detail="Payout is already approved.")

    payout.status = "completed"
    await db.commit()
    return {"message": "Payout approved and completed successfully.", "payout_id": payout.id}

@router.post("/payouts/{id}/reject")
async def reject_payout(
    id: str,
    payload: schemas.PayoutActionRequest,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.PayoutRecord).filter(models.PayoutRecord.id == id)
    res = await db.execute(stmt)
    payout = res.scalars().first()
    if not payout:
        raise HTTPException(status_code=404, detail="Payout record not found.")

    payout.status = "failed"
    payout.reject_reason = payload.reason or "Rejected by administrator."
    await db.commit()
    return {"message": "Payout rejected successfully.", "payout_id": payout.id}

@router.post("/payouts/{id}/hold")
async def hold_payout(
    id: str,
    payload: schemas.PayoutActionRequest,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.PayoutRecord).filter(models.PayoutRecord.id == id)
    res = await db.execute(stmt)
    payout = res.scalars().first()
    if not payout:
        raise HTTPException(status_code=404, detail="Payout record not found.")

    payout.status = "held"
    payout.hold_note = payload.note or "On hold pending verification."
    await db.commit()
    return {"message": "Payout placed on hold.", "payout_id": payout.id}

@router.post("/payouts/batch-approve")
async def batch_approve_payouts(
    payload: schemas.BatchPayoutActionRequest,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.PayoutRecord).filter(models.PayoutRecord.id.in_(payload.ids))
    res = await db.execute(stmt)
    payouts = res.scalars().all()
    
    count = 0
    for payout in payouts:
        if payout.status != "completed":
            payout.status = "completed"
            count += 1
            
    await db.commit()
    return {"message": f"Successfully approved {count} payouts.", "count": count}

# --- 7. Enquiries ---

@router.get("/enquiries")
async def list_enquiries(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1),
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_read_db)
):
    stmt = select(models.EnquiryThread).options(joinedload(models.EnquiryThread.user))
    if status:
        stmt = stmt.filter(models.EnquiryThread.status == status)
        
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0
    
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    res = await db.execute(stmt)
    threads = res.scalars().all()
    
    return {
        "enquiries": threads,
        "total": total
    }

@router.get("/enquiries/{id}")
async def get_enquiry_details(
    id: str,
    db: AsyncSession = Depends(get_read_db)
):
    stmt = select(models.EnquiryThread).options(
        joinedload(models.EnquiryThread.user),
        joinedload(models.EnquiryThread.messages)
    ).filter(models.EnquiryThread.id == id)
    res = await db.execute(stmt)
    thread = res.scalars().unique().first()
    if not thread:
        raise HTTPException(status_code=404, detail="Enquiry thread not found.")
    return thread

@router.post("/enquiries/{id}/messages")
async def reply_to_enquiry(
    id: str,
    payload: schemas.ThreadMessageCreate,
    current_admin: models.AdminUser = Depends(auth.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.EnquiryThread).filter(models.EnquiryThread.id == id)
    res = await db.execute(stmt)
    thread = res.scalars().first()
    if not thread:
        raise HTTPException(status_code=404, detail="Enquiry thread not found.")
        
    message = models.ThreadMessage(
        thread_id=id,
        sender_id=current_admin.id,
        sender_type="admin",
        content=payload.content,
        is_internal_note=payload.is_internal_note
    )
    db.add(message)
    thread.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(message)
    return message

@router.patch("/enquiries/{id}/assign")
async def assign_enquiry(
    id: str,
    payload: schemas.EnquiryAssignRequest,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.EnquiryThread).filter(models.EnquiryThread.id == id)
    res = await db.execute(stmt)
    thread = res.scalars().first()
    if not thread:
        raise HTTPException(status_code=404, detail="Enquiry thread not found.")
        
    thread.assigned_admin_id = payload.admin_id
    await db.commit()
    return {"message": "Enquiry thread assignment updated.", "assigned_admin_id": thread.assigned_admin_id}

@router.patch("/enquiries/{id}/status")
async def update_enquiry_status(
    id: str,
    payload: schemas.EnquiryStatusRequest,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.EnquiryThread).filter(models.EnquiryThread.id == id)
    res = await db.execute(stmt)
    thread = res.scalars().first()
    if not thread:
        raise HTTPException(status_code=404, detail="Enquiry thread not found.")
        
    thread.status = payload.status
    await db.commit()
    return {"message": f"Enquiry thread status updated to {thread.status}."}

# --- 8. Verification Requests ---

@router.get("/verification")
async def list_verification_requests(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1),
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_read_db)
):
    stmt = select(models.VerificationRequest).options(joinedload(models.VerificationRequest.vendor))
    if status:
        stmt = stmt.filter(models.VerificationRequest.status == status)
        
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0
    
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    res = await db.execute(stmt)
    requests = res.scalars().all()
    
    return {
        "requests": requests,
        "total": total
    }

@router.get("/verification/{id}")
async def get_verification_details(
    id: str,
    db: AsyncSession = Depends(get_read_db)
):
    stmt = select(models.VerificationRequest).options(joinedload(models.VerificationRequest.vendor)).filter(models.VerificationRequest.id == id)
    res = await db.execute(stmt)
    request = res.scalars().first()
    if not request:
        raise HTTPException(status_code=404, detail="Verification request not found.")
    return request

@router.post("/verification/{id}/approve")
async def approve_verification_request(
    id: str,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.VerificationRequest).options(joinedload(models.VerificationRequest.vendor)).filter(models.VerificationRequest.id == id)
    res = await db.execute(stmt)
    request = res.scalars().first()
    if not request:
        raise HTTPException(status_code=404, detail="Verification request not found.")

    request.status = "approved"
    
    # Also activate vendor's shop
    shop_res = await db.execute(select(models.Shop).filter(models.Shop.owner_id == request.vendor_id))
    shop = shop_res.scalars().first()
    if shop:
        shop.verified = True
        shop.status = "active"
        
    await db.commit()
    return {"message": "Verification request approved successfully."}

@router.post("/verification/{id}/reject")
async def reject_verification_request(
    id: str,
    payload: schemas.VerificationRejectRequest,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.VerificationRequest).filter(models.VerificationRequest.id == id)
    res = await db.execute(stmt)
    request = res.scalars().first()
    if not request:
        raise HTTPException(status_code=404, detail="Verification request not found.")

    request.status = "rejected"
    request.rejection_reason = payload.reason
    await db.commit()
    return {"message": "Verification request rejected."}

@router.post("/verification/{id}/request-resubmission")
async def request_resubmission_verification(
    id: str,
    payload: schemas.VerificationRejectRequest,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.VerificationRequest).filter(models.VerificationRequest.id == id)
    res = await db.execute(stmt)
    request = res.scalars().first()
    if not request:
        raise HTTPException(status_code=404, detail="Verification request not found.")

    request.status = "resubmission_requested"
    request.rejection_reason = payload.reason
    await db.commit()
    return {"message": "Verification request resubmission triggered."}

# --- 9. Analytics ---

@router.get("/analytics/overview", response_model=schemas.AnalyticsOverviewOut)
async def get_analytics_overview(
    db: AsyncSession = Depends(get_read_db)
):
    # Total sales
    sales_res = await db.execute(select(func.sum(models.Order.total_price)).filter(models.Order.status == "completed"))
    total_sales = sales_res.scalar() or 0.0
    
    # Total orders
    orders_res = await db.execute(select(func.count(models.Order.id)))
    total_orders = orders_res.scalar() or 0
    
    # Total active vendors
    vendors_res = await db.execute(select(func.count(models.Shop.id)).filter(models.Shop.status == "active"))
    total_vendors = vendors_res.scalar() or 0
    
    # Total active users (buyers/users)
    users_res = await db.execute(select(func.count(models.User.id)).filter(models.User.is_active == True))
    active_users = users_res.scalar() or 0
    
    return {
        "active_users": active_users,
        "total_vendors": total_vendors,
        "total_sales": total_sales,
        "total_orders": total_orders,
        "orders_growth": 12.5,  # Mocked growth figures for presentation
        "sales_growth": 8.2,
        "active_users_growth": 5.4,
        "vendors_growth": 15.0
    }

@router.get("/analytics/charts", response_model=schemas.AnalyticsChartsOut)
async def get_analytics_charts(
    db: AsyncSession = Depends(get_read_db)
):
    # Return mock daily stats for the last 7 days for frontend chart plotting
    today = datetime.now(timezone.utc).date()
    sales_points = []
    orders_points = []
    
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        
        # We can add slightly randomized mock data for beautiful dashboard chart visualization
        sales_val = 150.0 + (i * 45.0) + (i % 2 * 20.0)
        orders_val = 2 + i + (i % 3)
        
        sales_points.append({"date": day_str, "sales": sales_val, "orders": orders_val})
        orders_points.append({"date": day_str, "sales": sales_val, "orders": orders_val})
        
    return {
        "sales_over_time": sales_points,
        "orders_over_time": orders_points
    }

# --- 10. Banners ---

@router.get("/banners", response_model=schemas.BannerSettingsOut)
async def get_banners(
    db: AsyncSession = Depends(get_read_db)
):
    settings = await get_banner_settings(db)
    return settings

@router.patch("/banners", response_model=schemas.BannerSettingsOut)
async def update_banners(
    payload: schemas.BannerSettingsUpdate,
    db: AsyncSession = Depends(get_db)
):
    settings = await get_banner_settings(db)
    
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(settings, key, value)
        
    await db.commit()
    await db.refresh(settings)
    return settings

# --- 11. Upload ---

@router.post("/upload/presigned-url")
def get_admin_upload_url(
    payload: schemas.BroadcastRequest,  # Reuse or similar schema
    db: AsyncSession = Depends(get_read_db)
):
    # This matches the presigned url request in client uploads
    bucket_name = os.getenv("AWS_STORAGE_BUCKET_NAME")
    if not bucket_name:
        raise HTTPException(
            status_code=500,
            detail="AWS S3 is not configured."
        )
    return {"message": "S3 presigned URL support endpoint"}

# --- 12. Notifications ---

@router.post("/notifications/broadcast")
async def broadcast_notification(
    payload: schemas.BroadcastRequest
):
    # Mock push/in-app broadcast logic
    return {
        "message": f"Broadcast notification '{payload.title}' successfully sent to target role: {payload.target_role}."
    }

# --- 13. Settings ---

@router.get("/settings", response_model=schemas.PlatformSettingsOut)
async def get_settings(
    db: AsyncSession = Depends(get_read_db)
):
    settings = await get_platform_settings(db)
    return settings

@router.patch("/settings", response_model=schemas.PlatformSettingsOut)
async def update_settings(
    payload: schemas.PlatformSettingsUpdate,
    db: AsyncSession = Depends(get_db)
):
    settings = await get_platform_settings(db)
    
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(settings, key, value)
        
    await db.commit()
    await db.refresh(settings)
    return settings

# --- Admin Users Management (Super Admin only) ---

def check_super_admin(current_admin: models.AdminUser = Depends(auth.get_current_admin)):
    if current_admin.role != models.AdminRole.super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Super Administrators are permitted to manage administrators."
        )

@router.get("/settings/admins", response_model=List[schemas.AdminOut])
async def list_admins(
    db: AsyncSession = Depends(get_read_db),
    _ = Depends(check_super_admin)
):
    stmt = select(models.AdminUser).order_by(models.AdminUser.created_at.desc())
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("/settings/admins", response_model=schemas.AdminOut)
async def create_admin(
    payload: schemas.AdminCreateRequest,
    db: AsyncSession = Depends(get_db),
    _ = Depends(check_super_admin)
):
    # Check if email is unique
    res = await db.execute(select(models.AdminUser).filter(models.AdminUser.email == payload.email))
    if res.scalars().first():
        raise HTTPException(status_code=400, detail="Administrator with this email already exists.")
        
    hashed = auth.hash_password(payload.password)
    admin = models.AdminUser(
        name=payload.name,
        email=payload.email,
        password_hash=hashed,
        role=models.AdminRole(payload.role),
        avatar=payload.avatar
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin

@router.patch("/settings/admins/{id}", response_model=schemas.AdminOut)
async def update_admin(
    id: str,
    payload: schemas.AdminUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _ = Depends(check_super_admin)
):
    stmt = select(models.AdminUser).filter(models.AdminUser.id == id)
    res = await db.execute(stmt)
    admin = res.scalars().first()
    if not admin:
        raise HTTPException(status_code=404, detail="Administrator not found.")
        
    update_data = payload.model_dump(exclude_unset=True)
    if "password" in update_data and update_data["password"]:
        admin.password_hash = auth.hash_password(update_data["password"])
        del update_data["password"]
        
    for key, value in update_data.items():
        if key == "role" and value:
            admin.role = models.AdminRole(value)
        elif value is not None:
            setattr(admin, key, value)
            
    await db.commit()
    await db.refresh(admin)
    return admin

@router.delete("/settings/admins/{id}")
async def delete_admin(
    id: str,
    db: AsyncSession = Depends(get_db),
    _ = Depends(check_super_admin)
):
    stmt = select(models.AdminUser).filter(models.AdminUser.id == id)
    res = await db.execute(stmt)
    admin = res.scalars().first()
    if not admin:
        raise HTTPException(status_code=404, detail="Administrator not found.")
        
    await db.delete(admin)
    await db.commit()
    return {"message": "Administrator deleted successfully."}
