from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, List
from enum import Enum

class AdminRole(str, Enum):
    super_admin = "super_admin"
    admin = "admin"
    support = "support"

class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str

class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class AdminOut(BaseModel):
    id: str
    name: str
    email: str
    role: AdminRole
    avatar: Optional[str] = None
    last_login: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class AdminChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class AdminCreateRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: AdminRole
    avatar: Optional[str] = None

class AdminUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[AdminRole] = None
    avatar: Optional[str] = None

# Settings DTOs
class PlatformSettingsOut(BaseModel):
    commission_rate: float
    withdrawal_fee: float
    support_email: str
    maintenance_mode: bool
    updated_at: datetime

    class Config:
        from_attributes = True

class PlatformSettingsUpdate(BaseModel):
    commission_rate: Optional[float] = None
    withdrawal_fee: Optional[float] = None
    support_email: Optional[str] = None
    maintenance_mode: Optional[bool] = None

# Banner DTOs
class BannerSettingsOut(BaseModel):
    hero_title: str
    hero_description: str
    hero_image_src: str
    hero_variant: str
    hero_active: bool
    announcement_text: str
    announcement_link_label: Optional[str] = None
    announcement_link_href: Optional[str] = None
    announcement_style: str
    announcement_active: bool
    announcement_dismissible: bool
    updated_at: datetime

    class Config:
        from_attributes = True

class BannerSettingsUpdate(BaseModel):
    hero_title: Optional[str] = None
    hero_description: Optional[str] = None
    hero_image_src: Optional[str] = None
    hero_variant: Optional[str] = None
    hero_active: Optional[bool] = None
    announcement_text: Optional[str] = None
    announcement_link_label: Optional[str] = None
    announcement_link_href: Optional[str] = None
    announcement_style: Optional[str] = None
    announcement_active: Optional[bool] = None
    announcement_dismissible: Optional[bool] = None

# Verification DTOs
class VerificationRequestOut(BaseModel):
    id: str
    vendor_id: str
    status: str
    id_document_key: str
    selfie_key: str
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class VerificationRejectRequest(BaseModel):
    reason: str

# Enquiry DTOs
class ThreadMessageOut(BaseModel):
    id: str
    thread_id: str
    sender_id: str
    sender_type: str
    content: str
    is_internal_note: bool
    created_at: datetime

    class Config:
        from_attributes = True

class EnquiryThreadOut(BaseModel):
    id: str
    subject: str
    status: str
    assigned_admin_id: Optional[str] = None
    user_id: str
    created_at: datetime
    updated_at: datetime
    messages: List[ThreadMessageOut] = []

    class Config:
        from_attributes = True

class ThreadMessageCreate(BaseModel):
    content: str
    is_internal_note: bool = False

class EnquiryAssignRequest(BaseModel):
    admin_id: Optional[str] = None

class EnquiryStatusRequest(BaseModel):
    status: str

# Banning, Flagging, Removing DTOs
class BanRequest(BaseModel):
    reason: str

class FlagRequest(BaseModel):
    reason: str

class RemoveRequest(BaseModel):
    reason: str

# Payout DTOs
class PayoutActionRequest(BaseModel):
    reason: Optional[str] = None
    note: Optional[str] = None

class BatchPayoutActionRequest(BaseModel):
    ids: List[str]

# Notification DTOs
class BroadcastRequest(BaseModel):
    title: str
    message: str
    target_role: Optional[str] = "all"  # all, seller, customer

# Analytics DTOs
class AnalyticsOverviewOut(BaseModel):
    active_users: int
    total_vendors: int
    total_sales: float
    total_orders: int
    orders_growth: float
    sales_growth: float
    active_users_growth: float
    vendors_growth: float

class ChartDataPoint(BaseModel):
    date: str
    sales: float
    orders: int

class AnalyticsChartsOut(BaseModel):
    sales_over_time: List[ChartDataPoint]
    orders_over_time: List[ChartDataPoint]
