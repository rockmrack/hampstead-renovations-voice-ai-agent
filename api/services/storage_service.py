"""
AWS S3 storage service for audio files and documents.
"""

from typing import Optional
import uuid

import structlog

from config import settings

logger = structlog.get_logger(__name__)


class StorageService:
    """Service for AWS S3 storage operations."""

    def __init__(self):
        self.bucket = settings.aws_s3_bucket
        self.region = settings.aws_region
        self._client = None

    async def _get_client(self):
        """Get or create S3 client."""
        if self._client is None:
            import aioboto3
            session = aioboto3.Session()
            self._client = await session.client(
                "s3",
                region_name=self.region,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
            ).__aenter__()
        return self._client

    async def upload_audio(
        self,
        audio_data: bytes,
        filename: Optional[str] = None,
        content_type: str = "audio/mpeg",
    ) -> str:
        """
        Upload audio file to S3 and return public URL.
        
        Args:
            audio_data: Audio file bytes
            filename: Optional filename (generated if not provided)
            content_type: MIME type of audio
            
        Returns:
            Public URL of uploaded file
        """
        if not filename:
            filename = f"voice-notes/{uuid.uuid4()}.mp3"

        try:
            client = await self._get_client()
            
            await client.put_object(
                Bucket=self.bucket,
                Key=filename,
                Body=audio_data,
                ContentType=content_type,
                ACL="public-read",
            )

            url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{filename}"
            
            logger.info(
                "audio_uploaded",
                filename=filename,
                size=len(audio_data),
                url=url,
            )

            return url

        except Exception as e:
            logger.error("s3_upload_error", error=str(e))
            raise

    async def upload_document(
        self,
        data: bytes,
        filename: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload document to S3.
        
        Args:
            data: File bytes
            filename: S3 key/path
            content_type: MIME type
            
        Returns:
            Public URL
        """
        try:
            client = await self._get_client()
            
            await client.put_object(
                Bucket=self.bucket,
                Key=filename,
                Body=data,
                ContentType=content_type,
            )

            url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{filename}"
            
            logger.info("document_uploaded", filename=filename)
            return url

        except Exception as e:
            logger.error("s3_document_upload_error", error=str(e))
            raise

    async def get_presigned_url(
        self,
        filename: str,
        expires_in: int = 3600,
    ) -> str:
        """
        Generate presigned URL for private file access.
        
        Args:
            filename: S3 key
            expires_in: URL expiration in seconds
            
        Returns:
            Presigned URL
        """
        try:
            client = await self._get_client()
            
            url = await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": filename},
                ExpiresIn=expires_in,
            )

            return url

        except Exception as e:
            logger.error("s3_presigned_url_error", error=str(e))
            raise

    async def delete_file(self, filename: str) -> bool:
        """Delete a file from S3."""
        try:
            client = await self._get_client()
            
            await client.delete_object(
                Bucket=self.bucket,
                Key=filename,
            )

            logger.info("file_deleted", filename=filename)
            return True

        except Exception as e:
            logger.error("s3_delete_error", error=str(e))
            return False

    async def file_exists(self, filename: str) -> bool:
        """Check if a file exists in S3."""
        try:
            client = await self._get_client()
            
            await client.head_object(
                Bucket=self.bucket,
                Key=filename,
            )
            return True

        except Exception:
            return False


# Singleton instance
storage_service = StorageService()
