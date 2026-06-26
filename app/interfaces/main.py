import os
import sentry_sdk
import redis.asyncio as redis # type: ignore
from fastapi import FastAPI, Request, Response # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from fastapi.staticfiles import StaticFiles # type: ignore
from fastapi_limiter import FastAPILimiter # type: ignore
from arq import create_pool # type: ignore
from arq.connections import RedisSettings # type: ignore
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi import HTTPException
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)


from app.infrastructure.services.logging_service import setup_logging
from app.interfaces.middlewares.envelope import (
    EnvelopeMiddleware,
    http_exception_handler,
    starlette_http_exception_handler,
    validation_exception_handler,
)
from app.interfaces.routers.v1 import (
    auth as auth_router,
    product as product_router,
    category as category_router,
    cart as cart_router,
    order as order_router,
    review as review_router,
    wishlist as wishlist_router,
    payment as payment_router,
    escrow as escrow_router,
    search as search_router,
    config as config_router,
    upload as upload_router,
    admin as admin_router,
    admin_auth as admin_auth_router,
)

# 1. Setup Structured Logging
setup_logging()

# 2. Initialize Sentry Error Tracking if DSN is configured
SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN and SENTRY_DSN.startswith("http"):
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )

app = FastAPI(
    title="Afrovogue Commercial API",
    version="1.0",
    docs_url=None,
    redoc_url=None,
)


# Register global Bearer security scheme in OpenAPI schema for Swagger UI Authorize button
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Afrovogue Commercial API",
        version="1.0",
        routes=app.routes,
    )
    # Define the Bearer Auth scheme
    openapi_schema["components"] = openapi_schema.get("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter your access token here."
        }
    }
    # Assign BearerAuth globally to all routes
    for path in openapi_schema.get("paths", {}).values():
        for method in path.values():
            method["security"] = [{"BearerAuth": []}]
            
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url="/docs/oauth2-redirect",
        swagger_js_url="/static/docs/swagger-ui-bundle.js",
        swagger_css_url="/static/docs/swagger-ui.css",
        swagger_favicon_url="/static/docs/favicon.png",
    )

@app.get("/docs/oauth2-redirect", include_in_schema=False)
async def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()

@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - ReDoc",
        redoc_js_url="/static/docs/redoc.standalone.js",
        redoc_favicon_url="/static/docs/favicon.png",
    )

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

# 4. Add custom envelope middleware (inner layer)
app.add_middleware(EnvelopeMiddleware)

# Register CORSMiddleware last (outermost layer) so it handles all outgoing responses and exceptions
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 5. Add validation and exception handlers
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

@app.on_event("startup")
async def startup():
    """Initialize the rate limiter, redis cache, and background task worker pool on application startup."""
    redis_conn = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379"), encoding="utf-8", decode_responses=True)
    await FastAPILimiter.init(redis_conn)
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

app.include_router(auth_router.router)
app.include_router(product_router.router)
app.include_router(category_router.router)
app.include_router(cart_router.router)
app.include_router(order_router.router)
app.include_router(review_router.router)
app.include_router(wishlist_router.router)
app.include_router(payment_router.router)
app.include_router(escrow_router.router)
app.include_router(search_router.router)
app.include_router(config_router.router)
app.include_router(upload_router.router)
app.include_router(admin_router.router)
app.include_router(admin_auth_router.router)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root():
    return {"message": "Afrovogue API running"}
