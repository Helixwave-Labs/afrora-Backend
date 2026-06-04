from datetime import datetime, timezone
from typing import Optional

class UserDomainModel:
    def __init__(
        self,
        id: str,
        username: str,
        email: str,
        hashed_password: str,
        is_active: bool = False,
        otp: Optional[str] = None,
        otp_expires_at: Optional[datetime] = None,
        role: str = "customer",
        password_reset_token: Optional[str] = None,
        password_reset_token_expires_at: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
        profile_picture_url: Optional[str] = None,
        phone: Optional[str] = None,
        country: Optional[str] = None
    ):
        self.id = id
        self.username = username
        self.email = email
        self.hashed_password = hashed_password
        self.is_active = is_active
        self.otp = otp
        self.otp_expires_at = otp_expires_at
        self.role = role
        self.password_reset_token = password_reset_token
        self.password_reset_token_expires_at = password_reset_token_expires_at
        self.created_at = created_at
        self.profile_picture_url = profile_picture_url
        self.phone = phone
        self.country = country

    def verify_otp(self, input_otp: str, current_time: datetime) -> bool:
        if not self.otp or not self.otp_expires_at:
            return False
        if current_time > self.otp_expires_at:
            return False
        return self.otp == input_otp

    def activate(self) -> None:
        self.is_active = True
        self.otp = None
        self.otp_expires_at = None

    def set_reset_token(self, token: str, expires_at: datetime) -> None:
        self.password_reset_token = token
        self.password_reset_token_expires_at = expires_at

    def reset_password(self, new_hashed_password: str) -> None:
        self.hashed_password = new_hashed_password
        self.password_reset_token = None
        self.password_reset_token_expires_at = None
