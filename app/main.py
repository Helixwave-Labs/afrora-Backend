import os
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastAPIIntegration
from fastapi import FastAPI # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
import redis.asyncio as redis # type: ignore
from app.routes import user_routes, product_routes, category_routes, cart_routes, order_routes, review_routes, wishlist_routes, payment_routes, upload_routes
from app.database import Base, engine
from fastapi.staticfiles import StaticFiles # type: ignore
from fastapi_limiter import FastAPILimiter # type: ignore
from app.logging_config import setup_logging
from arq import create_pool # type: ignore
from arq.connections import RedisSettings # type: ignore

# 1. Setup Structured Logging
setup_logging()

# 2. Initialize Sentry Error Tracking if DSN is configured
SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[FastAPIIntegration()],
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )

app = FastAPI(title="Afrovogue Commercial API", version="1.0")

# 3. Setup CORS Middleware
origins = [
    org.strip() for org in os.getenv("ALLOWED_ORIGINS", "").split(",") if org.strip()
]
if not origins:
    origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    """Initialize the rate limiter, redis cache, and background task worker pool on application startup."""
    redis_conn = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379"), encoding="utf-8", decode_responses=True)
    await FastAPILimiter.init(redis_conn)
    
    # Store redis connection for caching support
    app.state.redis = redis_conn
    
    try:
        app.state.arq_pool = await create_pool(RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://redis:6379")))
    except Exception:
        app.state.arq_pool = None

@app.on_event("shutdown")
async def shutdown():
    """Gracefully close the redis and background task pool on application shutdown."""
    if hasattr(app.state, "redis") and app.state.redis:
        await app.state.redis.close()
    if hasattr(app.state, "arq_pool") and app.state.arq_pool:
        await app.state.arq_pool.close()


app.include_router(user_routes.router)
app.include_router(product_routes.router)
app.include_router(category_routes.router)
app.include_router(cart_routes.router)
app.include_router(order_routes.router)
app.include_router(review_routes.router)
app.include_router(wishlist_routes.router)
app.include_router(payment_routes.router)
app.include_router(upload_routes.router)


# Mount the 'static' directory to serve profile pictures locally if fallback is active
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root():
    return {"message": "Afrovogue API running"}

