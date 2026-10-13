from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal
from PIL import Image, UnidentifiedImageError
from io import BytesIO
from tempfile import NamedTemporaryFile
from pathlib import Path
import httpx

class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "KHIETTRAN AI STUDIO API"
    api_cors_origins: str = "http://localhost:1420,http://127.0.0.1:1420,tauri://localhost,http://tauri.localhost"
    max_upload_mb: int = 5
    ai_provider: str = "none"
    replicate_api_token: str = ""
    replicate_model_owner: str = "recraft-ai"
    replicate_model_name: str = "recraft-remove-background"
    replicate_image_input_field: str = "image"
    replicate_face_model_owner: str = "tencentarc"
    replicate_face_model_name: str = "gfpgan"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

settings = Settings()
app = FastAPI(title=settings.app_name, version="0.2.0", description="KHIETTRAN AI STUDIO API — MVP with optional Recraft background removal.")

origins = [x.strip() for x in settings.api_cors_origins.split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

class EditRequest(BaseModel):
    operation: Literal["portrait_retouch", "background_remove", "image_restore"]
    image_url: str = Field(min_length=8, max_length=2048, description="Reserved for future private-storage workflow.")
    strength: float = Field(default=0.5, ge=0, le=1)

def _provider_configured() -> bool:
    return bool(settings.ai_provider.lower() == "replicate" and settings.replicate_api_token)

@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name, "environment": settings.app_env}

@app.get("/api/v1/capabilities")
def capabilities():
    configured = _provider_configured()
    return {
        "app": settings.app_name,
        "api_version": "v1",
        "features": {
            "basic_color_adjustment": "client",
            "batch_ui": "client-scaffold",
            "portrait_retouch": "available" if configured else "provider-credentials-required",
            "background_remove": "available" if configured else "provider-credentials-required",
            "image_restore": "available" if configured else "provider-credentials-required"
        },
        "ai_provider": settings.ai_provider,
        "ai_provider_configured": configured,
        "background_model": f"{settings.replicate_model_owner}/{settings.replicate_model_name}",
        "portrait_model": f"{settings.replicate_face_model_owner}/{settings.replicate_face_model_name}",
        "restore_model": f"{settings.replicate_face_model_owner}/{settings.replicate_face_model_name}",
        "note": "Configured means a token exists; make a real test call before production use."
    }

def _validate_image_upload(file: UploadFile) -> tuple[bytes, str]:
    if not file.content_type or file.content_type.lower() not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="Chỉ hỗ trợ JPEG, PNG hoặc WEBP.")
    limit = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Tệp ảnh rỗng.")
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"Ảnh vượt quá giới hạn {settings.max_upload_mb} MB.")
    try:
        with Image.open(BytesIO(data)) as img:
            if img.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(status_code=415, detail="Định dạng ảnh không được hỗ trợ.")
            width, height = img.size
            if width > 4096 or height > 4096 or width * height > 16_000_000:
                raise HTTPException(status_code=413, detail="Ảnh vượt giới hạn 4096 px hoặc 16 megapixel.")
            img.verify()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(status_code=400, detail="Tệp không phải ảnh hợp lệ.")
    return data, {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[file.content_type.lower()]


def _run_image_model(data: bytes, suffix: str, model: str, input_field: str, extra_input: dict | None = None) -> bytes:
    try:
        import replicate
    except ImportError:
        raise HTTPException(status_code=503, detail="Thiếu thư viện replicate. Cài backend/requirements.txt.")
    temp_path = None
    try:
        with NamedTemporaryFile(suffix=suffix, delete=False) as temp:
            temp.write(data)
            temp.flush()
            temp_path = temp.name
        with open(temp_path, "rb") as image_handle:
            model_input = {input_field: image_handle}
            model_input.update(extra_input or {})
            output = replicate.run(model, input=model_input)
        if isinstance(output, (list, tuple)):
            output = output[0] if output else None
        if output is None:
            raise RuntimeError("Model returned no output.")
        if isinstance(output, (bytes, bytearray)):
            result_bytes = bytes(output)
        elif hasattr(output, "read"):
            result_bytes = output.read()
        else:
            output_url = output if isinstance(output, str) else (output.url() if callable(getattr(output, "url", None)) else None)
            if not isinstance(output_url, str) or not output_url.startswith("https://"):
                raise RuntimeError("Unsupported provider output type.")
            with httpx.Client(timeout=90, follow_redirects=False) as client:
                response = client.get(output_url)
                response.raise_for_status()
                result_bytes = response.content
        with Image.open(BytesIO(result_bytes)) as result_img:
            if result_img.format not in {"PNG", "JPEG", "WEBP"}:
                raise RuntimeError("Model output was not a supported image.")
            result_img.verify()
        with Image.open(BytesIO(result_bytes)) as result_img:
            normalized = BytesIO()
            result_img.convert("RGBA").save(normalized, format="PNG", optimize=True)
            return normalized.getvalue()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Nhà cung cấp AI chưa trả kết quả hợp lệ ({type(exc).__name__}).")
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass


def _require_provider():
    if not _provider_configured():
        raise HTTPException(status_code=503, detail="AI chưa được cấu hình. Thiết lập REPLICATE_API_TOKEN trong biến môi trường của máy chủ.")


@app.post("/api/v1/background/remove")
def remove_background(file: UploadFile = File(...)):
    """Remove image background using Recraft on Replicate. Returns PNG bytes with alpha."""
    _require_provider()
    data, suffix = _validate_image_upload(file)
    result = _run_image_model(data, suffix, f"{settings.replicate_model_owner}/{settings.replicate_model_name}", settings.replicate_image_input_field)
    return Response(content=result, media_type="image/png", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@app.post("/api/v1/portrait/retouch")
def portrait_retouch(file: UploadFile = File(...), strength: float = 0.5):
    """Face enhancement using GFPGAN; it improves facial detail but is not a dedicated skin-mask retoucher."""
    _require_provider()
    if not 0 <= strength <= 1:
        raise HTTPException(status_code=422, detail="strength phải nằm trong khoảng 0–1.")
    data, suffix = _validate_image_upload(file)
    result = _run_image_model(data, suffix, f"{settings.replicate_face_model_owner}/{settings.replicate_face_model_name}", "img", {"version": "v1.4", "scale": 2 if strength >= 0.5 else 1})
    return Response(content=result, media_type="image/png", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@app.post("/api/v1/image/restore")
def image_restore(file: UploadFile = File(...)):
    """Restore face details and upscale using GFPGAN v1.4."""
    _require_provider()
    data, suffix = _validate_image_upload(file)
    result = _run_image_model(data, suffix, f"{settings.replicate_face_model_owner}/{settings.replicate_face_model_name}", "img", {"version": "v1.4", "scale": 2})
    return Response(content=result, media_type="image/png", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

@app.post("/api/v1/edits")
def create_edit(req: EditRequest):
    if req.operation == "background_remove":
        raise HTTPException(status_code=501, detail="Dùng /api/v1/background/remove để tải ảnh lên an toàn.")
    if req.operation == "portrait_retouch":
        raise HTTPException(status_code=501, detail="Dùng /api/v1/portrait/retouch để tải ảnh lên an toàn.")
    raise HTTPException(status_code=501, detail="Dùng /api/v1/image/restore để tải ảnh lên an toàn.")
