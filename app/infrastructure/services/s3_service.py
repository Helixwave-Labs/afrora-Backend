import os
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from fastapi import HTTPException, UploadFile
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Support both Cloudflare R2 and AWS S3 environment variables
AWS_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("R2_REGION") or os.getenv("AWS_REGION") or "auto"
AWS_STORAGE_BUCKET_NAME = os.getenv("R2_BUCKET_NAME") or os.getenv("AWS_STORAGE_BUCKET_NAME")
AWS_S3_CUSTOM_DOMAIN = os.getenv("R2_CUSTOM_DOMAIN") or os.getenv("AWS_S3_CUSTOM_DOMAIN")
AWS_S3_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL") or os.getenv("AWS_S3_ENDPOINT_URL")

s3_client_kwargs = {
    "aws_access_key_id": AWS_ACCESS_KEY_ID,
    "aws_secret_access_key": AWS_SECRET_ACCESS_KEY,
    "region_name": AWS_REGION,
    "config": Config(signature_version="s3v4", s3={"addressing_style": "path"})
}
if AWS_S3_ENDPOINT_URL:
    s3_client_kwargs["endpoint_url"] = AWS_S3_ENDPOINT_URL

s3_client = boto3.client("s3", **s3_client_kwargs)

def upload_file_to_s3(file: UploadFile, folder: str = "general") -> str:
    if not AWS_STORAGE_BUCKET_NAME:
        raise HTTPException(status_code=500, detail="S3 bucket name is not configured.")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")

    unique_filename = f"{folder}/{int(datetime.utcnow().timestamp())}_{file.filename}"

    extra_args = {"ContentType": file.content_type}
    # Cloudflare R2 does not support S3 ACLs (like public-read)
    is_r2 = AWS_S3_ENDPOINT_URL and "r2.cloudflarestorage.com" in AWS_S3_ENDPOINT_URL
    if not is_r2:
        extra_args["ACL"] = "public-read"

    try:
        s3_client.upload_fileobj(
            file.file,
            AWS_STORAGE_BUCKET_NAME,
            unique_filename,
            ExtraArgs=extra_args
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"S3 Upload failed: {str(e)}")
    finally:
        file.file.close()

    if AWS_S3_CUSTOM_DOMAIN:
        return f"https://{AWS_S3_CUSTOM_DOMAIN}/{unique_filename}"
    if AWS_S3_ENDPOINT_URL:
        return f"{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/{unique_filename}"
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
        elif AWS_S3_ENDPOINT_URL and AWS_S3_ENDPOINT_URL in file_url:
            parts = file_url.split(f"{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/")
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

    is_r2 = AWS_S3_ENDPOINT_URL and "r2.cloudflarestorage.com" in AWS_S3_ENDPOINT_URL

    if is_r2:
        try:
            # R2 does not support presigned POST, generate presigned PUT instead
            url = s3_client.generate_presigned_url(
                ClientMethod="put_object",
                Params={
                    "Bucket": AWS_STORAGE_BUCKET_NAME,
                    "Key": unique_key,
                },
                ExpiresIn=3600
            )
            response_url = url
            response_fields = {}
        except ClientError as e:
            raise HTTPException(status_code=500, detail=f"Failed to generate presigned PUT URL: {str(e)}")
    else:
        fields = {"Content-Type": file_type, "acl": "public-read"}
        conditions = [
            {"Content-Type": file_type},
            ["content-length-range", 1, 10485760],
            {"acl": "public-read"}
        ]
        try:
            response = s3_client.generate_presigned_post(
                Bucket=AWS_STORAGE_BUCKET_NAME,
                Key=unique_key,
                Fields=fields,
                Conditions=conditions,
                ExpiresIn=3600
            )
            response_url = response["url"]
            response_fields = response["fields"]
        except ClientError as e:
            raise HTTPException(status_code=500, detail=f"Failed to generate presigned POST parameters: {str(e)}")

    if AWS_S3_CUSTOM_DOMAIN:
        public_url = f"https://{AWS_S3_CUSTOM_DOMAIN}/{unique_key}"
    elif AWS_S3_ENDPOINT_URL:
        public_url = f"{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/{unique_key}"
    else:
        public_url = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{unique_key}"

    return {
        "url": response_url,
        "fields": response_fields,
        "public_url": public_url,
        "key": unique_key
    }


def get_full_s3_url(path: str) -> str:
    if not path:
        return path
    if path.startswith("http://") or path.startswith("https://"):
        return path
        
    clean_path = path.lstrip("/")
    
    if AWS_S3_CUSTOM_DOMAIN:
        return f"https://{AWS_S3_CUSTOM_DOMAIN}/{clean_path}"
    if AWS_S3_ENDPOINT_URL:
        return f"{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/{clean_path}"
    return f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{clean_path}"
