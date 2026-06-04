from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request, Response, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta, timezone
import secrets
import shutil
import os
from pathlib import Path

from app.infrastructure.models import models
from app.application.dtos import user as schemas
from app.infrastructure.services import auth
from app.infrastructure.database.database import get_db, get_read_db
from app.infrastructure.services.s3_service import upload_file_to_s3, delete_file_from_s3
from app.infrastructure.services.email_service import generate_otp, send_verification_email, send_password_reset_email
from fastapi_limiter.depends import RateLimiter

from app.infrastructure.repositories.sqlalchemy_user_repository import SqlAlchemyUserRepository
from app.application.usecases.user_usecases import UserSignupUseCase, VerifyEmailUseCase, UserLoginUseCase

router = APIRouter(
    prefix="/auth",
    tags=["Auth"]
)

# Define constants for file paths to avoid magic strings
PROFILE_PICS_DIR = Path("static/profile_pics")
PROFILE_PICS_URL_PREFIX = "/static/profile_pics"

# Ensure the profile picture directory exists on startup
os.makedirs(PROFILE_PICS_DIR, exist_ok=True)

@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(
    user_data: schemas.UserSignup,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Creates a new buyer account under the role 'user'.
    """
    repo = SqlAlchemyUserRepository(db)
    use_case = UserSignupUseCase(repo)

    try:
        user = await use_case.execute(user_data.name, user_data.email, user_data.password)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Send verification email
    arq_pool = request.app.state.arq_pool if hasattr(request, "app") and hasattr(request.app.state, "arq_pool") else None
    if arq_pool:
        await arq_pool.enqueue_job("send_verification_email_task", user.email, user.otp)
    else:
        background_tasks.add_task(send_verification_email, user.email, user.otp)

    return {
        "user": {
            "id": user.id,
            "name": user.username,
            "email": user.email,
            "role": user.role
        }
    }

@router.post("/login")
async def login_for_access_token(
    login_data: schemas.LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_read_db)
):
    """
    Authenticates a user, sets the secure HttpOnly cookie, and returns the token.
    """
    repo = SqlAlchemyUserRepository(db)
    use_case = UserLoginUseCase(repo)

    try:
        user = await use_case.execute(login_data.email, login_data.password)
    except KeyError as e:
        if str(e) == "'AUTH_INVALID_CREDENTIALS'":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"message": "Incorrect email or password", "code": "AUTH_INVALID_CREDENTIALS"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Account not verified. Please check your email for the verification OTP.", "code": "AUTH_NOT_VERIFIED"}
        )

    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )

    # Set secure HttpOnly cookie
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=auth.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

    return {
        "user": {
            "id": user.id,
            "name": user.username,
            "email": user.email,
            "role": user.role
        },
        "access_token": access_token
    }

@router.post("/logout")
async def logout(response: Response):
    """
    Clears the access token cookie.
    """
    response.delete_cookie(key="access_token", httponly=True, samesite="strict")
    return {"message": "Logged out successfully"}

@router.get("/me")
async def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    """
    Get the profile details for the currently authenticated user.
    """
    return {
        "id": current_user.id,
        "name": current_user.username,
        "email": current_user.email,
        "role": current_user.role,
        "phone": getattr(current_user, "phone", "+233501234567"),
        "country": getattr(current_user, "country", "Ghana"),
        "createdAt": current_user.created_at.isoformat() if current_user.created_at else None
    }

@router.patch("/me")
async def update_user_profile(
    profile_data: schemas.ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Updates the authenticated user's profile details.
    """
    if profile_data.name is not None:
        current_user.username = profile_data.name
    if profile_data.phone is not None:
        current_user.phone = profile_data.phone
    if profile_data.country is not None:
        current_user.country = profile_data.country
    
    await db.commit()
    await db.refresh(current_user)
    
    return {
        "id": current_user.id,
        "name": current_user.username,
        "email": current_user.email,
        "role": current_user.role,
        "phone": getattr(current_user, "phone", "+233501234567"),
        "country": getattr(current_user, "country", "Ghana"),
        "createdAt": current_user.created_at.isoformat() if current_user.created_at else None
    }

@router.get("/all-users", response_model=list[schemas.UserOut])
async def get_all_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_read_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Retrieve a list of all users. Restrict to admins.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform this action."
        )

    stmt = select(models.User).offset(skip).limit(limit)
    result = await db.execute(stmt)
    users = result.scalars().all()
    return users

@router.post("/verify-email", status_code=status.HTTP_200_OK)
async def verify_email(verification_data: schemas.EmailVerification, db: AsyncSession = Depends(get_db)):
    repo = SqlAlchemyUserRepository(db)
    use_case = VerifyEmailUseCase(repo)

    try:
        await use_case.execute(verification_data.email, verification_data.otp)
        await db.commit()
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {"message": "Email verified successfully. You can now log in."}

@router.post(
    "/resend-otp",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(RateLimiter(times=1, minutes=1))]
)
async def resend_otp(
    payload: schemas.ResendOTPRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.User).filter(models.User.email == payload.email)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User with this email not found.")

    if user.is_active is True:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This account is already verified.")

    new_otp = generate_otp()
    user.otp = new_otp
    user.otp_expires_at = datetime.utcnow() + timedelta(minutes=10)
    await db.commit()

    arq_pool = request.app.state.arq_pool if hasattr(request, "app") and hasattr(request.app.state, "arq_pool") else None
    if arq_pool:
        await arq_pool.enqueue_job("send_verification_email_task", user.email, new_otp)
    else:
        background_tasks.add_task(send_verification_email, user.email, new_otp)

    return {"message": "A new verification OTP has been sent to your email."}

@router.post("/forgot-password", status_code=status.HTTP_200_OK, dependencies=[Depends(RateLimiter(times=1, minutes=1))])
async def forgot_password(
    payload: schemas.ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(models.User).filter(models.User.email == payload.email)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if user:
        token = secrets.token_urlsafe(32)
        user.password_reset_token = token
        user.password_reset_token_expires_at = datetime.utcnow() + timedelta(minutes=15)
        await db.commit()

        arq_pool = request.app.state.arq_pool if hasattr(request, "app") and hasattr(request.app.state, "arq_pool") else None
        if arq_pool:
            await arq_pool.enqueue_job("send_password_reset_email_task", user.email, token)
        else:
            background_tasks.add_task(send_password_reset_email, user.email, token)

    return {"message": "If an account with that email exists, a password reset link has been sent."}

@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(request: schemas.ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    stmt = select(models.User).filter(models.User.password_reset_token == request.token)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user or not user.password_reset_token_expires_at or datetime.utcnow() > user.password_reset_token_expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token."
        )

    hashed_password = auth.hash_password(request.new_password)
    user.hashed_password = hashed_password
    user.password_reset_token = None
    user.password_reset_token_expires_at = None

    if not user.is_active:
        user.is_active = True
        user.otp = None
        user.otp_expires_at = None

    await db.commit()

    return {"message": "Password has been reset successfully. You can now log in with your new password."}

@router.put("/me/profile-picture", status_code=status.HTTP_200_OK)
async def upload_profile_picture(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Please upload an image."
        )

    bucket_name = os.getenv("AWS_STORAGE_BUCKET_NAME")
    if bucket_name:
        if current_user.profile_picture_url:
            delete_file_from_s3(current_user.profile_picture_url)
        file_url = upload_file_to_s3(file, folder="profile_pics")
    else:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required")
        file_extension = Path(file.filename).suffix
        unique_filename = f"{current_user.id}_{int(datetime.utcnow().timestamp())}{file_extension}"
        file_path = PROFILE_PICS_DIR / unique_filename

        try:
            with file_path.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        finally:
            file.file.close()

        if current_user.profile_picture_url:
            old_picture_path = Path(current_user.profile_picture_url.lstrip('/'))
            if old_picture_path.exists() and old_picture_path.is_file():
                try:
                    os.remove(old_picture_path)
                except OSError:
                    pass

        file_url = f"{PROFILE_PICS_URL_PREFIX}/{unique_filename}"

    current_user.profile_picture_url = file_url
    await db.commit()

    return {"message": "Profile picture updated successfully.", "profile_picture_url": file_url}
