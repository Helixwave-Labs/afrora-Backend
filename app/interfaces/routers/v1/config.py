from fastapi import APIRouter, Depends, Request
from typing import Dict

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
