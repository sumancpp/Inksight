import os
import uuid
from pathlib import Path
from typing import Optional, Tuple
from fastapi import HTTPException, UploadFile, status

try:
    import magic
except ImportError:
    magic = None

from app.core.config import settings
from app.core.logging import logger
from app.services.malware_scanner import malware_scanner

ALLOWED_SIGNATURES = {
    "application/pdf": [b"%PDF-"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
}

CONTENT_TYPE_EXTENSIONS = {
    "application/pdf": [".pdf"],
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
}

EXTENSION_TO_CONTENT_TYPE = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


class StorageService:
    def __init__(self, upload_dir: Optional[str] = None):
        self._upload_dir_setting = upload_dir

    @property
    def upload_dir(self) -> Path:
        base_dir = Path(self._upload_dir_setting or settings.UPLOAD_DIR).resolve()
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    def sanitize_original_filename(self, filename: Optional[str]) -> str:
        if not filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename is missing or empty.",
            )
        clean_name = Path(filename).name
        if not clean_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid filename.",
            )
        return clean_name

    def validate_file_type_and_extension(
        self, filename: str, content_type: Optional[str]
    ) -> Tuple[str, str]:
        # Normalize content_type and handle common aliases
        ct = (content_type or "").lower().split(";")[0].strip()
        if ct == "image/jpg":
            ct = "image/jpeg"

        if ct not in settings.ALLOWED_UPLOAD_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported content type '{ct}'. Allowed types: PDF, JPEG, PNG.",
            )

        # Check extension
        ext = Path(filename).suffix.lower()
        if ext not in EXTENSION_TO_CONTENT_TYPE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file extension '{ext}'. Allowed extensions: .pdf, .jpg, .jpeg, .png.",
            )

        expected_ct = EXTENSION_TO_CONTENT_TYPE[ext]
        if expected_ct != ct:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mismatched file extension and content type.",
            )

        storage_ext = ".jpg" if ct == "image/jpeg" else ext
        return ct, storage_ext

    def validate_magic_bytes(self, header: bytes, content_type: str) -> None:
        signatures = ALLOWED_SIGNATURES.get(content_type, [])
        matched = any(header.startswith(sig) for sig in signatures)
        if not matched:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content signature does not match the declared file type.",
            )

    async def validate_upload(self, file: UploadFile) -> Tuple[str, str, str]:
        """
        Validates an uploaded file before saving:
        1. Validates filename and extension against allowed extensions (.pdf, .png, .jpg, .jpeg)
        2. Validates declared/provided file size against MAX_UPLOAD_SIZE_MB
        3. Inspects actual file header using python-magic to prevent extension spoofing
        4. Runs antivirus/malware scan stub
        5. Resets file stream pointer to 0 for downstream consumption
        """
        original_filename = self.sanitize_original_filename(file.filename)
        ext = Path(original_filename).suffix.lower()
        allowed_exts = getattr(settings, "ALLOWED_UPLOAD_EXTENSIONS", [".pdf", ".png", ".jpg", ".jpeg"])
        if ext not in allowed_exts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file extension '{ext}'. Allowed extensions: .pdf, .png, .jpg, .jpeg.",
            )

        max_bytes = getattr(settings, "MAX_UPLOAD_SIZE_BYTES", settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024)
        if file.size is not None and file.size > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB ({max_bytes} bytes).",
            )

        # Inspect header bytes
        header = await file.read(2048)
        if not header:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty.",
            )

        # Magic number inspection via python-magic
        detected_mime = None
        if magic is not None:
            try:
                detected_mime = magic.from_buffer(header, mime=True)
            except Exception as exc:
                logger.warning(f"python-magic inspection error, falling back: {exc}")
                detected_mime = None

        if detected_mime == "image/jpg":
            detected_mime = "image/jpeg"

        allowed_mimes = ["application/pdf", "image/png", "image/jpeg"]
        if detected_mime:
            if detected_mime not in allowed_mimes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File content signature '{detected_mime}' does not match allowed types. Only application/pdf, image/png, and image/jpeg are permitted.",
                )
            expected_mime = EXTENSION_TO_CONTENT_TYPE.get(ext)
            if expected_mime and detected_mime != expected_mime:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File content signature '{detected_mime}' does not match extension '{ext}'.",
                )
        else:
            expected_mime = EXTENSION_TO_CONTENT_TYPE.get(ext, "")
            self.validate_magic_bytes(header, expected_mime)

        content_type = detected_mime or EXTENSION_TO_CONTENT_TYPE[ext]
        storage_ext = ".jpg" if content_type == "image/jpeg" else ext

        # Run malware scan stub
        if not malware_scanner.scan_file(header):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Malware scan detected suspicious content.",
            )

        # Reset stream pointer
        await file.seek(0)
        return original_filename, content_type, storage_ext

    async def save_upload(
        self, file: UploadFile
    ) -> Tuple[str, str, str, str, int]:
        """
        Validates and saves an uploaded file stream chunk by chunk.
        Enforces maximum upload size and cleans up partially written files on error.

        Returns:
            Tuple of (original_filename, stored_filename, storage_path, content_type, file_size_bytes)
        """
        original_filename, content_type, storage_ext = await self.validate_upload(file)

        # Generate unique server-side filename
        stored_filename = f"{uuid.uuid4().hex}{storage_ext}"
        target_dir = self.upload_dir
        target_path = (target_dir / stored_filename).resolve()

        # Prevent path traversal outside storage directory
        if not target_path.is_relative_to(target_dir):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid storage destination.",
            )

        max_bytes = getattr(settings, "MAX_UPLOAD_SIZE_BYTES", settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024)
        total_bytes = 0

        try:
            with open(target_path, "wb") as f:
                while True:
                    chunk = await file.read(64 * 1024)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB ({max_bytes} bytes).",
                        )
                    f.write(chunk)
        except Exception:
            # Clean up partially written file on any failure
            if target_path.exists():
                try:
                    target_path.unlink()
                except OSError:
                    pass
            raise

        logger.info(
            f"Successfully stored upload '{stored_filename}' ({total_bytes} bytes) for '{original_filename}'"
        )

        storage_path = str(target_path)

        # If S3 backend is configured, upload to S3 and return the S3 URL
        if getattr(settings, "STORAGE_BACKEND", "local").lower() == "s3":
            try:
                s3_url = self._upload_to_s3(target_path, stored_filename, content_type, original_filename)
                storage_path = s3_url
                logger.info(f"Successfully uploaded '{stored_filename}' to S3: {s3_url}")
            except Exception as exc:
                if target_path.exists():
                    try:
                        target_path.unlink()
                    except OSError:
                        pass
                logger.error(f"S3 upload failed for '{stored_filename}': {exc}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Cloud storage upload failed: {str(exc)}",
                )

        return (
            original_filename,
            stored_filename,
            storage_path,
            content_type,
            total_bytes,
        )

    def _get_s3_client(self):
        import boto3
        client_kwargs = {
            "region_name": getattr(settings, "AWS_REGION", "us-east-1"),
        }
        if getattr(settings, "AWS_ACCESS_KEY_ID", None) and getattr(settings, "AWS_SECRET_ACCESS_KEY", None):
            client_kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
            client_kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
        if getattr(settings, "S3_ENDPOINT_URL", None):
            client_kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
        return boto3.client("s3", **client_kwargs)

    def _upload_to_s3(self, file_path: Path, stored_filename: str, content_type: str, original_filename: str) -> str:
        bucket = getattr(settings, "S3_BUCKET_NAME", None)
        if not bucket:
            raise ValueError("S3_BUCKET_NAME must be specified when STORAGE_BACKEND is 's3'.")

        s3 = self._get_s3_client()
        with open(file_path, "rb") as f:
            s3.upload_fileobj(
                f,
                bucket,
                stored_filename,
                ExtraArgs={
                    "ContentType": content_type,
                    "Metadata": {"original_filename": original_filename},
                },
            )

        endpoint = getattr(settings, "S3_ENDPOINT_URL", None)
        if endpoint:
            return f"{endpoint.rstrip('/')}/{bucket}/{stored_filename}"
        region = getattr(settings, "AWS_REGION", "us-east-1")
        return f"https://{bucket}.s3.{region}.amazonaws.com/{stored_filename}"

    def get_file_path(self, stored_filename: str) -> Path:
        target_dir = self.upload_dir
        file_path = (target_dir / stored_filename).resolve()
        if not file_path.is_relative_to(target_dir):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stored file not found.",
            )
        if not file_path.exists() and getattr(settings, "STORAGE_BACKEND", "local").lower() == "s3":
            bucket = getattr(settings, "S3_BUCKET_NAME", None)
            if bucket:
                try:
                    s3 = self._get_s3_client()
                    s3.download_file(bucket, stored_filename, str(file_path))
                except Exception as exc:
                    logger.error(f"Failed to fetch {stored_filename} from S3: {exc}")
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Stored file not found in cloud storage.",
                    )
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stored file not found.",
            )
        return file_path

    def delete_file(self, stored_filename: str) -> bool:
        deleted = False
        if getattr(settings, "STORAGE_BACKEND", "local").lower() == "s3":
            bucket = getattr(settings, "S3_BUCKET_NAME", None)
            if bucket:
                try:
                    s3 = self._get_s3_client()
                    s3.delete_object(Bucket=bucket, Key=stored_filename)
                    deleted = True
                except Exception as e:
                    logger.warning(f"Failed to delete '{stored_filename}' from S3: {e}")
        try:
            target_dir = self.upload_dir
            file_path = (target_dir / stored_filename).resolve()
            if file_path.is_relative_to(target_dir) and file_path.exists():
                file_path.unlink()
                deleted = True
        except Exception as e:
            logger.warning(f"Failed to delete file '{stored_filename}': {e}")
        return deleted


storage_service = StorageService()
