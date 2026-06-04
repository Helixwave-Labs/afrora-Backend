from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta, timezone

from app.infrastructure.models import models
from app.application.dtos import admin as schemas
from app.infrastructure.services import auth
from app.infrastructure.database.database import get_db, get_read_db

router = APIRouter(
    prefix="/auth/admin",
    tags=["Admin Auth"]
)

@router.post("/login", response_model=schemas.AdminLoginResponse)
async def admin_login(
    payload: schemas.AdminLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(models.AdminUser).filter(models.AdminUser.email == payload.email))
    admin = result.scalars().first()
    
    if not admin or not auth.verify_password(payload.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Incorrect email or password.", "code": "AUTH_INVALID_CREDENTIALS"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Update last login time
    admin.last_login = datetime.now(timezone.utc)
    await db.commit()

    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": admin.email, "role": admin.role.value},
        expires_delta=access_token_expires
    )
    
    # 7 days expiration for refresh token
    refresh_token_expires = timedelta(days=7)
    refresh_token = auth.create_access_token(
        data={"sub": admin.email, "type": "refresh"},
        expires_delta=refresh_token_expires
    )

    # Set secure HttpOnly cookies
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=auth.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=7 * 24 * 60 * 60
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.post("/refresh", response_model=schemas.AdminLoginResponse)
async def admin_refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_read_db)
):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        # Fallback to authorization header if any
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            refresh_token = auth_header.split(" ")[1]
            
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is missing."
        )

    try:
        payload = auth.jwt.decode(refresh_token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type.")
        email = payload.get("sub")
    except auth.JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.")

    result = await db.execute(select(models.AdminUser).filter(models.AdminUser.email == email))
    admin = result.scalars().first()
    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not found.")

    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": admin.email, "role": admin.role.value},
        expires_delta=access_token_expires
    )

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=auth.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.post("/logout")
async def admin_logout(response: Response):
    response.delete_cookie(key="access_token", httponly=True, samesite="strict")
    response.delete_cookie(key="refresh_token", httponly=True, samesite="strict")
    return {"message": "Logged out successfully"}

@router.get("/me", response_model=schemas.AdminOut)
async def admin_me(current_admin: models.AdminUser = Depends(auth.get_current_admin)):
    return current_admin

@router.post("/change-password")
async def admin_change_password(
    payload: schemas.AdminChangePasswordRequest,
    current_admin: models.AdminUser = Depends(auth.get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    if not auth.verify_password(payload.current_password, current_admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password."
        )

    current_admin.password_hash = auth.hash_password(payload.new_password)
    await db.commit()
    return {"message": "Password changed successfully"}
