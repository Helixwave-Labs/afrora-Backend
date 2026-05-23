import os
import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, UploadFile
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# AWS S3 Settings loaded from environment
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME")
AWS_S3_CUSTOM_DOMAIN = os.getenv("AWS_S3_CUSTOM_DOMAIN") # For CloudFront integration

s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

def upload_file_to_s3(file: UploadFile, folder: str = "general") -> str:
    """
    Uploads a file directly to the S3 bucket and returns the public URL.
    """
    if not AWS_STORAGE_BUCKET_NAME:
        raise HTTPException(status_code=500, detail="S3 bucket name is not configured.")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")

    file_extension = Path(file.filename).suffix
    unique_filename = f"{folder}/{int(datetime.utcnow().timestamp())}_{file.filename}"

    try:
        s3_client.upload_fileobj(
            file.file,
            AWS_STORAGE_BUCKET_NAME,
            unique_filename,
            ExtraArgs={
                "ContentType": file.content_type,
                "ACL": "public-read"
            }
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"S3 Upload failed: {str(e)}")
    finally:
        file.file.close()

    if AWS_S3_CUSTOM_DOMAIN:
        return f"https://{AWS_S3_CUSTOM_DOMAIN}/{unique_filename}"
    return f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{unique_filename}"


def delete_file_from_s3(file_url: Optional[str]) -> bool:
    """
    Parses the file URL to get the S3 object key and deletes the object.
    """
    if not file_url or not AWS_STORAGE_BUCKET_NAME:
        return False

    # Example URL: https://bucket-name.s3.region.amazonaws.com/folder/filename.jpg
    # Or CDN: https://cdn.domain.com/folder/filename.jpg
    try:
        if AWS_S3_CUSTOM_DOMAIN and AWS_S3_CUSTOM_DOMAIN in file_url:
            key = file_url.split(f"https://{AWS_S3_CUSTOM_DOMAIN}/")[-1]
        elif f"https://{AWS_STORAGE_BUCKET_NAME}.s3." in file_url:
            # Splits at region.amazonaws.com/
            parts = file_url.split(".amazonaws.com/")
            if len(parts) > 1:
                key = parts[-1]
            else:
                return False
        else:
            return False

        s3_client.delete_object(Bucket=AWS_STORAGE_BUCKET_NAME, Key=key)
        return True
    except ClientError:
        # Silently fail in deletion as it's often clean-up logic
        return False


def generate_presigned_post_data(file_name: str, file_type: str, folder: str = "general") -> Dict[str, Any]:
    """
    Generates a presigned URL and POST fields that the frontend can use to upload directly to S3.
    """
    if not AWS_STORAGE_BUCKET_NAME:
        raise HTTPException(status_code=500, detail="S3 bucket name is not configured.")

    file_extension = Path(file_name).suffix
    unique_key = f"{folder}/{int(datetime.utcnow().timestamp())}_{file_name}"

    try:
        response = s3_client.generate_presigned_post(
            Bucket=AWS_STORAGE_BUCKET_NAME,
            Key=unique_key,
            Fields={
                "acl": "public-read",
                "Content-Type": file_type
            },
            Conditions=[
                {"acl": "public-read"},
                {"Content-Type": file_type},
                ["content-length-range", 1, 10485760] # Limit to 10MB
            ],
            ExpiresIn=3600 # 1 hour validity
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate presigned POST parameters: {str(e)}")

    # Add custom CDN domain to public url if configured
    if AWS_S3_CUSTOM_DOMAIN:
        public_url = f"https://{AWS_S3_CUSTOM_DOMAIN}/{unique_key}"
    else:
        public_url = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{unique_key}"

    return {
        "url": response["url"],
        "fields": response["fields"],
        "public_url": public_url,
        "key": unique_key
    }
