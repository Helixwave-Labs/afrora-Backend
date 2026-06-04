import os
import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, UploadFile
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME")
AWS_S3_CUSTOM_DOMAIN = os.getenv("AWS_S3_CUSTOM_DOMAIN")

s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

def upload_file_to_s3(file: UploadFile, folder: str = "general") -> str:
    if not AWS_STORAGE_BUCKET_NAME:
        raise HTTPException(status_code=500, detail="S3 bucket name is not configured.")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")

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
    if not file_url or not AWS_STORAGE_BUCKET_NAME:
        return False

    try:
        if AWS_S3_CUSTOM_DOMAIN and AWS_S3_CUSTOM_DOMAIN in file_url:
            key = file_url.split(f"https://{AWS_S3_CUSTOM_DOMAIN}/")[-1]
        elif f"https://{AWS_STORAGE_BUCKET_NAME}.s3." in file_url:
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
        return False


def generate_presigned_post_data(file_name: str, file_type: str, folder: str = "general") -> Dict[str, Any]:
    if not AWS_STORAGE_BUCKET_NAME:
        raise HTTPException(status_code=500, detail="S3 bucket name is not configured.")

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
                ["content-length-range", 1, 10485760]
            ],
            ExpiresIn=3600
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate presigned POST parameters: {str(e)}")

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
