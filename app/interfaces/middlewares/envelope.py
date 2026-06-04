import json
import os
import sentry_sdk
from fastapi import Request, Response, HTTPException, FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError

class EnvelopeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/openapi.json") or path.startswith("/static"):
            return await call_next(request)

        response = await call_next(request)

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            if isinstance(response, StreamingResponse):
                return response

            body = b""
            async for chunk in response.body_iterator:
                body += chunk

            try:
                data = json.loads(body.decode("utf-8"))
                
                if not isinstance(data, dict) or "success" not in data:
                    wrapped_data = {
                        "success": True,
                        "info": data
                    }
                    new_response = JSONResponse(
                        content=wrapped_data,
                        status_code=response.status_code
                    )
                    for header, val in response.headers.items():
                        if header.lower() != "content-length":
                            new_response.headers[header] = val
                    return new_response
                else:
                    return Response(
                        content=body,
                        status_code=response.status_code,
                        media_type="application/json",
                        headers=dict(response.headers)
                    )
            except Exception:
                return Response(
                    content=body,
                    status_code=response.status_code,
                    media_type="application/json",
                    headers=dict(response.headers)
                )

        return response

async def http_exception_handler(request: Request, exc: HTTPException):
    code = "ERROR"
    if exc.headers:
        code = exc.headers.get("X-Error-Code", "ERROR")
    
    message = exc.detail
    if isinstance(exc.detail, dict):
        message = exc.detail.get("message", str(exc.detail))
        code = exc.detail.get("code", code)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "info": {
                "message": message,
                "code": code
            }
        }
    )

async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "info": {
                "message": str(exc.detail),
                "code": "HTTP_ERROR"
            }
        }
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    message = "Request validation failed"
    if errors:
        err = errors[0]
        loc = " -> ".join(str(l) for l in err.get("loc", []))
        message = f"Validation error at {loc}: {err.get('msg')}"

    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "info": {
                "message": message,
                "code": "VALIDATION_ERROR"
            }
        }
    )
