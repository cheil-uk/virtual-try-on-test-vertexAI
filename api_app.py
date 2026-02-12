import base64
import io
import os
import time
from typing import Optional

import google.auth
from google.auth.transport.requests import Request
from typing import Any
import numpy as np
from PIL import Image, ImageFilter, ImageOps, ImageEnhance, ImageDraw
from rembg import remove, new_session

# Pillow resampling enum changed across versions; normalize to a single name.
# Pillow resampling enum changed across versions; normalize to a single name.
Resampling: Any
try:
    from PIL.Image import Resampling as _Resampling
    Resampling = _Resampling
except Exception:
    class _ResamplingFallback:
        LANCZOS = Image.LANCZOS  # type: ignore[attr-defined]

    Resampling = _ResamplingFallback
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Default models + basic image sizing guard
# Default models + basic image sizing guard
MODEL_ID = "virtual-try-on-001"
IMAGEN_MODEL_ID = os.environ.get("IMAGEN_MODEL_ID", "imagen-4.0-ultra-generate-001")
MAX_IMAGE_DIM = int(os.environ.get("MAX_IMAGE_DIM", "1280"))


# Request/response schemas for FastAPI
class TryOnRequest(BaseModel):
    # Required Vertex identifiers
    project: str = Field(..., description="GCP project ID")
    location: str = Field("us-central1", description="Vertex AI region")
    model: str = Field(MODEL_ID, description="Model ID")
    # Base64-encoded images (data URL already stripped)
    personImageBase64: str
    garmentImageBase64: str
    # Optional background controls
    backgroundPrompt: Optional[str] = None
    backgroundImageBase64: Optional[str] = None


class TryOnResponse(BaseModel):
    # Base64-encoded output image
    imageBase64: str


class BackgroundRequest(BaseModel):
    # Imagen generation parameters
    project: str = Field(..., description="GCP project ID")
    location: str = Field("us-central1", description="Vertex AI region")
    model: str = Field(IMAGEN_MODEL_ID, description="Imagen model ID")
    prompt: str
    sampleCount: int = 1


class BackgroundResponse(BaseModel):
    # Base64-encoded background + optional echo of prompt
    imageBase64: str
    prompt: Optional[str] = None


# FastAPI app + permissive CORS for local dev
app = FastAPI(title="Virtual Try-On API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Resolve an OAuth token (ADC preferred, env var fallback)
def resolve_token() -> str:
    # Prefer ADC (gcloud auth / service account) for auto-refreshing tokens
    try:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        if not credentials.valid or credentials.expired:
            credentials.refresh(Request())
        if credentials.token:
            return credentials.token
    except Exception:
        pass

    # Fallback: allow manual access token in env for local testing
    token = os.environ.get("ACCESS_TOKEN")
    if not token:
        raise HTTPException(
            status_code=401,
            detail=(
                "Missing access token. Run `gcloud auth application-default login` "
                "or set ACCESS_TOKEN."
            ),
        )
    return token


# Resize and compress images to keep API payloads reasonable
def resize_and_encode(base64_str: str, max_dim: int = MAX_IMAGE_DIM) -> str:
    # Decode base64 -> image, resize to max dimension, re-encode as JPEG
    image_bytes = base64.b64decode(base64_str)
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image.thumbnail((max_dim, max_dim))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# Composite the try-on output onto a generated background
def composite_on_background(
    foreground_b64: str,
    background_b64: str,
) -> str:
    # Decode input images
    fg_bytes = base64.b64decode(foreground_b64)
    bg_bytes = base64.b64decode(background_b64)

    foreground = Image.open(io.BytesIO(fg_bytes)).convert("RGBA")
    background = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")

    # Remove background from the try-on output for cleaner compositing.
    foreground_bytes = io.BytesIO()
    foreground.save(foreground_bytes, format="PNG")
    session = new_session("u2net")
    cutout_result = remove(
        foreground_bytes.getvalue(),
        session=session,
        alpha_matting=True,
        alpha_matting_foreground_threshold=240,
        alpha_matting_background_threshold=10,
        alpha_matting_erode_size=10,
    )
    if isinstance(cutout_result, bytes):
        foreground = Image.open(io.BytesIO(cutout_result)).convert("RGBA")
    elif isinstance(cutout_result, Image.Image):
        foreground = cutout_result.convert("RGBA")
    elif isinstance(cutout_result, np.ndarray):
        foreground = Image.fromarray(cutout_result).convert("RGBA")
    else:
        raise TypeError(f"Unexpected rembg output type: {type(cutout_result)}")

    # Fit background to the foreground aspect ratio without stretching.
    # Slight zoom-in helps the subject feel more grounded in the scene.
    zoom = 1.35
    bg_zoom = background.resize(
        (int(background.width * zoom), int(background.height * zoom)),
        Resampling.LANCZOS,
    )
    bg = ImageOps.fit(bg_zoom, foreground.size, Resampling.LANCZOS)

    # Scale subject to sit naturally in the scene (tweak as needed)
    scale = 0.78
    fg_target = (
        int(foreground.width * scale),
        int(foreground.height * scale),
    )
    fg = foreground.resize(fg_target, Resampling.LANCZOS)

    # Edge cleanup without creating a visible halo.
    fg_alpha = fg.split()[-1]
    fg_alpha = fg_alpha.point(lambda a: 255 if a > 200 else a)  # type: ignore[operator]
    fg.putalpha(fg_alpha)

    # Ground shadow: soft ellipse under feet to avoid rectangular artifacts.
    shadow = Image.new("RGBA", fg.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    fg_w = int(fg.width)
    fg_h = int(fg.height)
    ellipse_width = int(fg_w * 0.55)
    ellipse_height = int(fg_h * 0.08)
    ellipse_x = (fg.width - ellipse_width) // 2
    ellipse_y = int(fg_h * 0.88)
    shadow_draw.ellipse(
        (ellipse_x, ellipse_y, ellipse_x + ellipse_width, ellipse_y + ellipse_height),
        fill=(0, 0, 0, 120),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))

    offset = ((bg.width - fg.width) // 2, int(bg.height * 0.14))
    shadow_offset = (offset[0], offset[1])

    # Slight color matching to background brightness
    bg_luma = ImageOps.grayscale(bg).resize((1, 1)).getpixel((0, 0))
    fg_luma = ImageOps.grayscale(fg).resize((1, 1)).getpixel((0, 0))
    if isinstance(bg_luma, tuple):
        bg_luma = bg_luma[0]
    if isinstance(fg_luma, tuple):
        fg_luma = fg_luma[0]
    if bg_luma is None or fg_luma is None:
        bg_luma = 128
        fg_luma = 128
    bg_luma = float(bg_luma)
    fg_luma = float(fg_luma)
    if fg_luma > 0:
        brightness = max(0.85, min(1.15, bg_luma / fg_luma))
        fg = ImageEnhance.Brightness(fg).enhance(brightness)

    bg.alpha_composite(shadow, dest=shadow_offset)
    bg.alpha_composite(fg, dest=offset)

    # Return a JPEG result to keep sizes manageable
    output = bg.convert("RGB")
    buffer = io.BytesIO()
    output.save(buffer, format="JPEG", quality=92, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# Build the Vertex Virtual Try-On payload
def build_payload(person_b64: str, garment_b64: str, background_prompt: Optional[str]) -> dict:
    # Construct the payload expected by the Virtual Try-On model
    payload = {
        "instances": [
            {
                "personImage": {"image": {"bytesBase64Encoded": person_b64}},
                "productImages": [{"image": {"bytesBase64Encoded": garment_b64}}],
            }
        ],
        "parameters": {"sampleCount": 1},
    }

    # Virtual Try-On does not currently use prompt, but kept for completeness
    if background_prompt:
        payload["parameters"]["backgroundPrompt"] = background_prompt

    return payload


# Call Vertex AI publisher model endpoint
def call_vertex(project: str, location: str, model: str, token: str, payload: dict) -> dict:
    # Generic helper for Vertex publisher model predict endpoint
    url = (
        "https://{location}-aiplatform.googleapis.com/v1/projects/"
        "{project}/locations/{location}/publishers/google/models/{model}:predict"
    ).format(location=location, project=project, model=model)

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    response = requests.post(url, headers=headers, json=payload, timeout=120)
    if not response.ok:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


# Simple health check for local dev
@app.get("/health")
def health() -> dict:
    # Basic liveness check for local dev / health probes
    return {"status": "ok", "time": int(time.time())}


# Try-on endpoint: calls Vertex Try-On, then optionally composites onto background
@app.post("/try-on", response_model=TryOnResponse)
def try_on(request: TryOnRequest) -> TryOnResponse:
    # Main try-on flow: normalize inputs, call Vertex, composite if needed
    token = resolve_token()

    # Normalize inputs so we don't exceed response size limits
    person_b64 = resize_and_encode(request.personImageBase64)
    garment_b64 = resize_and_encode(request.garmentImageBase64)

    payload = build_payload(person_b64, garment_b64, request.backgroundPrompt)
    response_json = call_vertex(
        project=request.project,
        location=request.location,
        model=request.model,
        token=token,
        payload=payload,
    )

    predictions = response_json.get("predictions", [])
    if not predictions:
        raise HTTPException(status_code=502, detail="No predictions returned from API.")

    image_payload = predictions[0].get("bytesBase64Encoded")
    if not image_payload:
        raise HTTPException(status_code=502, detail="Missing image data in API response.")

    # If a background was generated, composite it here
    if request.backgroundImageBase64:
        image_payload = composite_on_background(
            image_payload, request.backgroundImageBase64
        )

    return TryOnResponse(imageBase64=image_payload)


# Background endpoint: uses Imagen to create a scene from a prompt
@app.post("/background", response_model=BackgroundResponse)
def generate_background(request: BackgroundRequest) -> BackgroundResponse:
    # Imagen flow: prompt -> background image
    token = resolve_token()

    payload = {
        "instances": [{"prompt": request.prompt}],
        "parameters": {"sampleCount": request.sampleCount},
    }

    response_json = call_vertex(
        project=request.project,
        location=request.location,
        model=request.model,
        token=token,
        payload=payload,
    )

    predictions = response_json.get("predictions", [])
    if not predictions:
        raise HTTPException(status_code=502, detail="No predictions returned from API.")

    image_payload = predictions[0].get("bytesBase64Encoded")
    if not image_payload:
        raise HTTPException(status_code=502, detail="Missing image data in API response.")

    return BackgroundResponse(
        imageBase64=image_payload,
        prompt=predictions[0].get("prompt"),
    )
