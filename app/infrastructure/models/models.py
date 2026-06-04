import uuid
import enum
from sqlalchemy import Integer, String, Float, ForeignKey, Boolean, DateTime, func, CheckConstraint, UniqueConstraint, Numeric, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.infrastructure.database.database import Base

def generate_prefixed_id(prefix: str) -> str:
    """Generates a highly-compact, collision-resistant custom prefixed ID."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True, default=lambda: generate_prefixed_id("usr"))
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    otp: Mapped[str | None] = mapped_column(String, nullable=True)
    otp_expires_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False, server_default="customer")  # admin, seller, customer
    password_reset_token: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    password_reset_token_expires_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    profile_picture_url: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # Afróra Expanded Columns
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    ban_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    products: Mapped[list["Product"]] = relationship("Product", back_populates="owner")
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="user")
    wishlist_items: Mapped[list["WishlistItem"]] = relationship("WishlistItem", back_populates="user", cascade="all, delete-orphan")
    cart: Mapped["Cart"] = relationship("Cart", back_populates="user", uselist=False, cascade="all, delete-orphan")
    shop: Mapped["Shop | None"] = relationship("Shop", back_populates="owner", uselist=False, cascade="all, delete-orphan")

class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True, default=lambda: generate_prefixed_id("shp"))
    owner_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    banner_url: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # Escrow Bank Info
    bank_name: Mapped[str | None] = mapped_column(String, nullable=True)
    account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    account_number: Mapped[str | None] = mapped_column(String, nullable=True)
    
    status: Mapped[str] = mapped_column(String, default="pending")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    gmv: Mapped[float] = mapped_column(Float, default=0.0)
    orders_count: Mapped[int] = mapped_column(Integer, default=0)
    products_count: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    pending_balance: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped["User"] = relationship("User", back_populates="shop")
    products: Mapped[list["Product"]] = relationship("Product", back_populates="shop", cascade="all, delete-orphan")

class Category(Base):
    __tablename__ = "categories"
    
    id: Mapped[str] = mapped_column(String, primary_key=True, index=True, default=lambda: generate_prefixed_id("cat"))
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    subcategories: Mapped[list["SubCategory"]] = relationship("SubCategory", back_populates="category", cascade="all, delete-orphan")

class SubCategory(Base):
    __tablename__ = "subcategories"
    
    id: Mapped[str] = mapped_column(String, primary_key=True, index=True, default=lambda: generate_prefixed_id("sub"))
    name: Mapped[str] = mapped_column(String, index=True)
    category_id: Mapped[str] = mapped_column(String, ForeignKey("categories.id", ondelete="CASCADE"))

    category: Mapped["Category"] = relationship("Category", back_populates="subcategories")
    products: Mapped[list["Product"]] = relationship("Product", back_populates="subcategory")

class Product(Base):
    __tablename__ = "products"
    
    id: Mapped[str] = mapped_column(String, primary_key=True, index=True, default=lambda: generate_prefixed_id("prd"))
    name: Mapped[str] = mapped_column(String, index=True)
    description: Mapped[str] = mapped_column(String)
    price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer, CheckConstraint('quantity >= 0'), nullable=False, default=0)
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    is_removed: Mapped[bool] = mapped_column(Boolean, default=False)
    remove_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    
    owner_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subcategory_id: Mapped[str] = mapped_column(String, ForeignKey("subcategories.id"), index=True)
    shop_id: Mapped[str | None] = mapped_column(String, ForeignKey("shops.id", ondelete="CASCADE"), nullable=True, index=True)

    owner: Mapped["User"] = relationship("User", back_populates="products")
    shop: Mapped["Shop | None"] = relationship("Shop", back_populates="products")
    subcategory: Mapped["SubCategory"] = relationship("SubCategory", back_populates="products")
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="product", cascade="all, delete-orphan")

class Order(Base):
    __tablename__ = "orders"
    
    id: Mapped[str] = mapped_column(String, primary_key=True, index=True, default=lambda: generate_prefixed_id("ord"))
    user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    total_price: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending") # e.g., pending, processing, shipped, delivered, cancelled
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User")
    items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    escrow: Mapped["Escrow | None"] = relationship("Escrow", back_populates="order", uselist=False, cascade="all, delete-orphan")

class OrderItem(Base):
    __tablename__ = "order_items"
    
    id: Mapped[str] = mapped_column(String, primary_key=True, index=True, default=lambda: generate_prefixed_id("ori"))
    order_id: Mapped[str] = mapped_column(String, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[str | None] = mapped_column(String, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, CheckConstraint('quantity > 0'), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False) # Price at the time of purchase

    order: Mapped["Order"] = relationship("Order", back_populates="items")
    product: Mapped["Product"] = relationship("Product")

class Cart(Base):
    __tablename__ = "carts"
    
    id: Mapped[str] = mapped_column(String, primary_key=True, index=True, default=lambda: generate_prefixed_id("crt"))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="cart")
    items: Mapped[list["CartItem"]] = relationship("CartItem", back_populates="cart", cascade="all, delete-orphan")

class CartItem(Base):
    __tablename__ = "cart_items"
    
    id: Mapped[str] = mapped_column(String, primary_key=True, index=True, default=lambda: generate_prefixed_id("cri"))
    cart_id: Mapped[str] = mapped_column(String, ForeignKey("carts.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[str] = mapped_column(String, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, CheckConstraint('quantity > 0'), nullable=False)

    cart: Mapped["Cart"] = relationship("Cart", back_populates="items")
    product: Mapped["Product"] = relationship("Product")

class Review(Base):
    __tablename__ = "reviews"
    
    id: Mapped[str] = mapped_column(String, primary_key=True, index=True, default=lambda: generate_prefixed_id("rev"))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[str] = mapped_column(String, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, CheckConstraint('rating >= 1 AND rating <= 5'), nullable=False)
    comment: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="reviews")
    product: Mapped["Product"] = relationship("Product", back_populates="reviews")

    __table_args__ = (UniqueConstraint('user_id', 'product_id', name='_user_product_uc'),)

class WishlistItem(Base):
    __tablename__ = "wishlist_items"
    
    id: Mapped[str] = mapped_column(String, primary_key=True, index=True, default=lambda: generate_prefixed_id("wsh"))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[str] = mapped_column(String, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="wishlist_items")
    product: Mapped["Product"] = relationship("Product")

    __table_args__ = (UniqueConstraint('user_id', 'product_id', name='_user_product_wishlist_uc'),)

class Escrow(Base):
    __tablename__ = "escrows"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True, default=lambda: generate_prefixed_id("esc"))
    order_id: Mapped[str] = mapped_column(String, ForeignKey("orders.id", ondelete="CASCADE"), unique=True, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="held")  # held, released, refunded, disputed
    
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inspection_ends_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="escrow")
    dispute: Mapped["Dispute | None"] = relationship("Dispute", back_populates="escrow", uselist=False, cascade="all, delete-orphan")

class Dispute(Base):
    __tablename__ = "disputes"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True, default=lambda: generate_prefixed_id("dsp"))
    escrow_id: Mapped[str] = mapped_column(String, ForeignKey("escrows.id", ondelete="CASCADE"), unique=True, index=True)
    buyer_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")  # open, resolved, rejected
    priority: Mapped[str] = mapped_column(String, nullable=False, default="low")
    resolution_details: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    escrow: Mapped["Escrow"] = relationship("Escrow", back_populates="dispute")
    buyer: Mapped["User"] = relationship("User")

class PayoutRecord(Base):
    __tablename__ = "payout_records"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True, default=lambda: generate_prefixed_id("pay"))
    shop_id: Mapped[str] = mapped_column(String, ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")  # pending, completed, failed
    reference: Mapped[str | None] = mapped_column(String, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    hold_note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class AdminRole(str, enum.Enum):
    super_admin = "super_admin"
    admin = "admin"
    support = "support"

class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[AdminRole] = mapped_column(Enum(AdminRole), default=AdminRole.support)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_login: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class VerificationRequest(Base):
    __tablename__ = "verification_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_prefixed_id("ver"))
    vendor_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending, approved, rejected, resubmission_requested
    id_document_key: Mapped[str] = mapped_column(String(500))
    selfie_key: Mapped[str] = mapped_column(String(500))
    rejection_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    vendor: Mapped["User"] = relationship("User")

class EnquiryThread(Base):
    __tablename__ = "enquiry_threads"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_prefixed_id("enq"))
    subject: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String, default="open")  # open, closed, pending
    assigned_admin_id: Mapped[str | None] = mapped_column(String, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship("User")
    assigned_admin: Mapped["AdminUser | None"] = relationship("AdminUser")
    messages: Mapped[list["ThreadMessage"]] = relationship("ThreadMessage", back_populates="thread", cascade="all, delete-orphan")

class ThreadMessage(Base):
    __tablename__ = "thread_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_prefixed_id("msg"))
    thread_id: Mapped[str] = mapped_column(String, ForeignKey("enquiry_threads.id", ondelete="CASCADE"))
    sender_id: Mapped[str] = mapped_column(String)  # Can be User.id or AdminUser.id
    sender_type: Mapped[str] = mapped_column(String)  # user, admin
    content: Mapped[str] = mapped_column(String)
    is_internal_note: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    thread: Mapped["EnquiryThread"] = relationship("EnquiryThread", back_populates="messages")

class BannerSettings(Base):
    __tablename__ = "banner_settings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="singleton")
    hero_title: Mapped[str] = mapped_column(String(200), default="Welcome to Afróra!")
    hero_description: Mapped[str] = mapped_column(String(500), default="Discover unique items from Africa's top designers.")
    hero_image_src: Mapped[str] = mapped_column(String(500), default="/images/promo/welcome.png")
    hero_variant: Mapped[str] = mapped_column(String(20), default="welcome")
    hero_active: Mapped[bool] = mapped_column(Boolean, default=True)
    announcement_text: Mapped[str] = mapped_column(String(160), default="")
    announcement_link_label: Mapped[str | None] = mapped_column(String(60), nullable=True)
    announcement_link_href: Mapped[str | None] = mapped_column(String(200), nullable=True)
    announcement_style: Mapped[str] = mapped_column(String(20), default="default")
    announcement_active: Mapped[bool] = mapped_column(Boolean, default=False)
    announcement_dismissible: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class PlatformSettings(Base):
    __tablename__ = "platform_settings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="singleton")
    commission_rate: Mapped[float] = mapped_column(Float, default=0.05)
    withdrawal_fee: Mapped[float] = mapped_column(Float, default=1.0)
    support_email: Mapped[str] = mapped_column(String(254), default="support@afrora.com")
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class EscrowLog(Base):
    __tablename__ = "escrow_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_prefixed_id("log"))
    order_id: Mapped[str] = mapped_column(String, ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String)  # released, refunded, extended, flagged
    admin_id: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str] = mapped_column(String)
    amount: Mapped[float] = mapped_column(Float)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
