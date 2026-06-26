from fastapi import APIRouter, Depends, Request
from typing import Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.infrastructure.models import models
from app.infrastructure.database.database import get_read_db, AsyncSessionLocalWrite
from app.application.dtos import admin as admin_schemas

router = APIRouter(
    prefix="/config",
    tags=["System Config"]
)

@router.get("/exchange-rates")
async def get_exchange_rates(request: Request):
    redis_conn = getattr(request.app.state, "redis", None)
    if redis_conn:
        try:
            cached = await redis_conn.get("config:exchange_rates")
            if cached:
                import json
                return json.loads(cached)
        except Exception:
            pass

    rates = {
        "USD": 0.083,
        "EUR": 0.076,
        "NGN": 125.0,
        "GHS": 1.0
    }

    if redis_conn:
        try:
            import json
            await redis_conn.setex("config:exchange_rates", 86400, json.dumps(rates))
        except Exception:
            pass

    return rates

@router.get("/banners", response_model=admin_schemas.BannerSettingsOut)
async def get_config_banners(db: AsyncSession = Depends(get_read_db)):
    res = await db.execute(select(models.BannerSettings).filter(models.BannerSettings.id == "singleton"))
    settings = res.scalars().first()
    if not settings:
        async with AsyncSessionLocalWrite() as write_db:
            res_write = await write_db.execute(select(models.BannerSettings).filter(models.BannerSettings.id == "singleton"))
            settings = res_write.scalars().first()
            if not settings:
                settings = models.BannerSettings(id="singleton")
                write_db.add(settings)
                await write_db.commit()
                await write_db.refresh(settings)
                
    from app.infrastructure.services.s3_service import get_full_s3_url
    dto = admin_schemas.BannerSettingsOut.model_validate(settings)
    dto.hero_image_src = get_full_s3_url(dto.hero_image_src)
    return dto

