import logging
from typing import Optional

import boto3
from botocore.client import Config

from ..core.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """
    Backblaze B2 (S3-compatible) storage layer.
    Public method signatures match the previous GCS implementation so the
    rest of the app is untouched.
    """

    _client = None

    @classmethod
    def get_client(cls):
        if cls._client is None:
            logger.info("Initializing B2/S3 client (endpoint=%s)", settings.B2_ENDPOINT_URL)
            cls._client = boto3.client(
                "s3",
                endpoint_url=settings.B2_ENDPOINT_URL,
                aws_access_key_id=settings.B2_ACCESS_KEY_ID,
                aws_secret_access_key=settings.B2_SECRET_ACCESS_KEY,
                region_name=settings.B2_REGION,
                config=Config(
                    signature_version="s3v4",
                    connect_timeout=10,
                    read_timeout=60,
                    retries={"max_attempts": 2, "mode": "standard"},
                ),
            )
        return cls._client

    @classmethod
    def upload_file(
        cls,
        file_content: bytes,
        destination_path: str,
        content_type: Optional[str] = None,
    ) -> str:
        extra = {"ContentType": content_type} if content_type else {}
        cls.get_client().put_object(
            Bucket=settings.B2_BUCKET_NAME,
            Key=destination_path,
            Body=file_content,
            **extra,
        )
        return destination_path

    @classmethod
    def get_signed_url(
        cls,
        file_path: str,
        expiration_minutes: int = 60,
        inline: bool = False,
    ) -> str:
        disposition = "inline" if inline else "attachment"
        filename = file_path.rsplit("/", 1)[-1]
        return cls.get_client().generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.B2_BUCKET_NAME,
                "Key": file_path,
                "ResponseContentDisposition": f'{disposition}; filename="{filename}"',
            },
            ExpiresIn=expiration_minutes * 60,
        )

    @classmethod
    def delete_file(cls, file_path: str) -> None:
        cls.get_client().delete_object(
            Bucket=settings.B2_BUCKET_NAME,
            Key=file_path,
        )
