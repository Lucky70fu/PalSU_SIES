"""Upload validation helpers for private student/payment documents."""
from django.core.exceptions import ValidationError
from django.conf import settings

MAX_UPLOAD_SIZE = 5 * 1024 * 1024
_ALLOWED = {
    ".pdf": ("application/pdf",),
    ".png": ("image/png",),
    ".jpg": ("image/jpeg",),
    ".jpeg": ("image/jpeg",),
}


def validate_document_upload(uploaded):
    if not uploaded:
        return uploaded
    if uploaded.size > MAX_UPLOAD_SIZE:
        raise ValidationError("File must be 5 MB or smaller.")
    name = uploaded.name.lower()
    extension = ".jpeg" if name.endswith(".jpeg") else ".jpg" if name.endswith(".jpg") else ".png" if name.endswith(".png") else ".pdf" if name.endswith(".pdf") else ""
    if extension not in _ALLOWED:
        raise ValidationError("Upload a PDF, PNG, or JPEG file.")
    content_type = getattr(uploaded, "content_type", "")
    if content_type and content_type not in _ALLOWED[extension]:
        raise ValidationError("The uploaded file type does not match its extension.")
    try:
        uploaded.seek(0)
        head = uploaded.read(16)
        uploaded.seek(0)
    except Exception:
        raise ValidationError("The uploaded file could not be read.")
    valid = (
        (extension == ".pdf" and head.startswith(b"%PDF-"))
        or (extension == ".png" and head.startswith(b"\x89PNG\r\n\x1a\n"))
        or (extension in (".jpg", ".jpeg") and head.startswith(b"\xff\xd8\xff"))
    )
    if not valid:
        raise ValidationError("The file contents do not match a supported PDF, PNG, or JPEG format.")

    # Optional ClamAV scan. Configure CLAMAV_HOST/CLAMAV_PORT and install
    # python-clamd in deployments where antivirus scanning is required.
    if getattr(settings, "CLAMAV_REQUIRED", False) or getattr(settings, "CLAMAV_HOST", ""):
        try:
            import clamd
            scanner = clamd.ClamdNetworkSocket(
                host=settings.CLAMAV_HOST or "127.0.0.1",
                port=int(getattr(settings, "CLAMAV_PORT", 3310)),
                timeout=10,
            )
            uploaded.seek(0)
            result = scanner.scan_stream(uploaded.read())
            uploaded.seek(0)
            if result and list(result.values())[0][0] == "FOUND":
                raise ValidationError("The uploaded file was flagged by the malware scanner.")
        except ValidationError:
            raise
        except Exception as exc:
            uploaded.seek(0)
            if getattr(settings, "CLAMAV_REQUIRED", False):
                raise ValidationError("Malware scanning is required but the scanner is unavailable.") from exc
    return uploaded
