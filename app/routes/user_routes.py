from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request, UploadFile, File, Query
from sqlalchemy.orm import Session, Query as SQLAlchemyQuery
from datetime import datetime, timedelta
import secrets
import shutil
import os
from pathlib import Path

from app import models, schemas, auth
from app.database import get_db
from app.s3_utils import upload_file_to_s3, delete_file_from_s3
from app.email_utils import generate_otp, send_verification_email, send_password_reset_email
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_limiter.depends import RateLimiter

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)

# Define constants for file paths to avoid magic strings
PROFILE_PICS_DIR = Path("static/profile_pics")
PROFILE_PICS_URL_PREFIX = "/static/profile_pics"

# Ensure the profile picture directory exists on startup
os.makedirs(PROFILE_PICS_DIR, exist_ok=True)

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.UserOut)
async def create_user(
    user: schemas.UserCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db)
):
    # Check if user with that email or username already exists
    existing_user = db.query(models.User).filter(
        (models.User.email == user.email) | (models.User.username == user.username)
    ).first()
    if existing_user:
        if existing_user.email == user.email:
            raise HTTPException(status_code=400, detail="Email already registered")
        if existing_user.username == user.username:
            raise HTTPException(status_code=400, detail="Username already taken")

    # Hash the password
    hashed_password = auth.hash_password(user.password)

    # Generate OTP
    otp = generate_otp()
    otp_expires_at = datetime.utcnow() + timedelta(minutes=10) # OTP valid for 10 minutes

    # Create new user instance
    new_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        otp=otp,
        otp_expires_at=otp_expires_at
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Send verification email using ARQ queue (or fallback to BackgroundTasks)
    arq_pool = request.app.state.arq_pool if hasattr(request, "app") and hasattr(request.app.state, "arq_pool") else None
    if arq_pool:
        await arq_pool.enqueue_job("send_verification_email_task", new_user.email, otp)
    else:
        background_tasks.add_task(send_verification_email, new_user.email, otp)

    return new_user

@router.get("/", response_model=list[schemas.UserOut])
def get_all_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Retrieve a list of all users.
    This endpoint is restricted to admin users.
    Supports pagination with `skip` and `limit` query parameters.
    """
    # NOTE: This assumes your User model has a 'role' attribute.
    # If your role system is different (e.g., a separate roles table),
    # adjust this check accordingly.
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform this action."
        )

    users_query: SQLAlchemyQuery = db.query(models.User)
    users = users_query.offset(skip).limit(limit).all()
    return users

@router.post("/verify-email", status_code=status.HTTP_200_OK)
def verify_email(verification_data: schemas.EmailVerification, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == verification_data.email).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    
    if user.is_active is True:
        return {"message": "Account already verified."}

    if user.otp != verification_data.otp or not user.otp_expires_at or datetime.utcnow() > user.otp_expires_at:  # type: ignore
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP.")

    user.is_active = True
    user.otp = None # Clear OTP after successful verification
    user.otp_expires_at = None
    db.commit()

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
    db: Session = Depends(get_db)
):
    """
    Resends the One-Time Password (OTP) to a user's email if their account is not yet verified.
    """
    user = db.query(models.User).filter(models.User.email == payload.email).first()

    if not user:
        # Note: Returning a 404 can allow for email enumeration. In a production
        # environment, you might consider always returning a 200 OK response
        # to prevent attackers from discovering which emails are registered.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User with this email not found.")

    if user.is_active is True:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This account is already verified.")

    # Generate a new OTP, update it and its expiration in the database
    new_otp = generate_otp()
    user.otp = new_otp
    user.otp_expires_at = datetime.utcnow() + timedelta(minutes=10)  # type: ignore
    db.commit()

    # Send the new OTP email using ARQ queue (or fallback to BackgroundTasks)
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
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.email == payload.email).first()

    # To prevent email enumeration, always return a success message,
    # but only perform actions if the user exists.
    if user:
        # Generate a secure, URL-safe token
        token = secrets.token_urlsafe(32)
        user.password_reset_token = token
        user.password_reset_token_expires_at = datetime.utcnow() + timedelta(minutes=15)  # type: ignore
        db.commit()

        # Send the email using ARQ queue (or fallback to BackgroundTasks)
        arq_pool = request.app.state.arq_pool if hasattr(request, "app") and hasattr(request.app.state, "arq_pool") else None
        if arq_pool:
            await arq_pool.enqueue_job("send_password_reset_email_task", user.email, token)
        else:
            background_tasks.add_task(send_password_reset_email, user.email, token)

    return {"message": "If an account with that email exists, a password reset link has been sent."}

@router.post("/reset-password", status_code=status.HTTP_200_OK)
def reset_password(request: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    # Find the user by the reset token
    user = db.query(models.User).filter(models.User.password_reset_token == request.token).first()

    # Check if token is valid and not expired
    if not user or not user.password_reset_token_expires_at or datetime.utcnow() > user.password_reset_token_expires_at:  # type: ignore
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token."
        )

    # Hash the new password
    hashed_password = auth.hash_password(request.new_password)
    user.hashed_password = hashed_password

    # Invalidate the token after use
    user.password_reset_token = None
    user.password_reset_token_expires_at = None

    # If the user was inactive (e.g., never verified), activating them
    # upon password reset can be a good user experience.
    if not user.is_active:
        user.is_active = True
        user.otp = None
        user.otp_expires_at = None

    db.commit()

    return {"message": "Password has been reset successfully. You can now log in with your new password."}

@router.post("/login", response_model=schemas.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()

    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account not verified. Please check your email for the verification OTP."
        )

    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=schemas.UserOut)
def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    """
    Get the profile details for the currently authenticated user.
    """
    return current_user


@router.put("/me/profile-picture", status_code=status.HTTP_200_OK)
def upload_profile_picture(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Upload or update the current user's profile picture.
    Uses AWS S3 if configured, falling back to local storage if not.
    """
    # 1. Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Please upload an image."
        )

    # 2. Check if S3 is configured
    bucket_name = os.getenv("AWS_STORAGE_BUCKET_NAME")
    if bucket_name:
        # Delete the old S3 profile picture if it exists
        if current_user.profile_picture_url:
            delete_file_from_s3(current_user.profile_picture_url)
        # Upload new file to S3
        file_url = upload_file_to_s3(file, folder="profile_pics")
    else:
        # Fallback to local storage
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

        # Delete the old local file if it exists
        if current_user.profile_picture_url:
            old_picture_path = Path(current_user.profile_picture_url.lstrip('/'))
            if old_picture_path.exists() and old_picture_path.is_file():
                try:
                    os.remove(old_picture_path)
                except OSError:
                    pass

        file_url = f"{PROFILE_PICS_URL_PREFIX}/{unique_filename}"

    # 3. Update the user's record in the database
    current_user.profile_picture_url = file_url
    db.commit()

    return {"message": "Profile picture updated successfully.", "profile_picture_url": file_url}