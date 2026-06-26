from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.infrastructure.services import auth
from app.infrastructure.models import models
from app.infrastructure.services.s3_service import generate_presigned_post_data
import os

router = APIRouter(
    prefix="/uploads",
    tags=["Uploads"]
)

class PresignedUrlRequest(BaseModel):
    file_name: str
    file_type: str
    folder: str = "general"

@router.post("/presigned-url", status_code=status.HTTP_200_OK)
def get_presigned_upload_url(
    payload: PresignedUrlRequest,
    current_user: models.User = Depends(auth.get_current_user)
):
    bucket_name = os.getenv("R2_BUCKET_NAME") or os.getenv("AWS_STORAGE_BUCKET_NAME")
    if not bucket_name:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Direct uploads are disabled because AWS S3/R2 is not configured."
        )

    if payload.folder not in ["profile_pics", "product_images", "general"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid folder destination specified."
        )

    safe_file_name = f"{current_user.id}_{payload.file_name}"
    
    presigned_data = generate_presigned_post_data(
        file_name=safe_file_name,
        file_type=payload.file_type,
        folder=payload.folder
    )
    return presigned_data
