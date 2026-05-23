from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app import auth, models
from app.s3_utils import generate_presigned_post_data
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
    """
    Generate a presigned S3 POST URL so the client can upload
    media files directly to S3. This completely bypasses the FastAPI server.
    """
    bucket_name = os.getenv("AWS_STORAGE_BUCKET_NAME")
    if not bucket_name:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Direct uploads are disabled because AWS S3 is not configured."
        )

    # Restrict folder to safe categories
    if payload.folder not in ["profile_pics", "product_images", "general"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid folder destination specified."
        )

    # Build unique filename prefixed with user ID
    safe_file_name = f"{current_user.id}_{payload.file_name}"
    
    presigned_data = generate_presigned_post_data(
        file_name=safe_file_name,
        file_type=payload.file_type,
        folder=payload.folder
    )
    return presigned_data
