from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime
from typing import Optional

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserSignup(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None

class UserOut(BaseModel):
    profile_picture_url: Optional[str] = None
    id: str
    username: str
    email: EmailStr
    is_active: bool
    role: str
    created_at: datetime

    @field_validator("profile_picture_url")
    @classmethod
    def resolve_profile_picture_url(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        from app.infrastructure.services.s3_service import get_full_s3_url
        return get_full_s3_url(v)

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class EmailVerification(BaseModel):
    email: EmailStr
    otp: str

class ResendOTPRequest(BaseModel):
    email: EmailStr

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
