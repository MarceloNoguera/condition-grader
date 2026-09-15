import os
import base64
import json
import traceback
from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic

app = FastAPI(title="Device Condition Grader", version="1.0.0")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal error: {type(exc).__name__}: {str(exc)}"}
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static files
app.mount("/static", StaticFiles(directory="static"), name="static")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

PRICING = {
    "smartphone": {"Flawless": (250, 320), "Good": (150, 220), "Used": (60, 130), "Damaged": (10, 50)},
    "laptop":     {"Flawless": (500, 700), "Good": (300, 480), "Used": (150, 280), "Damaged": (30, 100)},
    "tablet":     {"Flawless": (200, 300), "Good": (120, 190), "Used": (50, 110), "Damaged": (10, 40)},
    "unknown":    {"Flawless": (100, 200), "Good": (60, 120),  "Used": (20, 60),  "Damaged": (5, 20)},
}

SYSTEM_PROMPT = """You are an expert electronics grader for a trade-in platform.
Analyze the provided image of a used electronic device and grade its physical condition.

Respond ONLY with a valid JSON object with these exact fields:
{
  "device_type": "smartphone | laptop | tablet | unknown",
  "brand": "detected brand or Unknown",
  "model": "detected model or Unknown",
  "grade": "Flawless | Good | Used | Damaged",
  "confidence": <integer 0-100>,
  "issues": ["list of detected physical issues, empty array if none"],
  "positives": ["list of positive condition notes"],
  "summary": "One sentence summary of the device condition"
}

Grading criteria:
- Flawless: Like new, no visible scratches, dents, or wear. Screen pristine.
- Good: Minor scratches or light wear, fully functional appearance.
- Used: Visible scratches, scuffs, or moderate wear. No cracks.
- Damaged: Cracked screen, broken parts, heavy damage.

Be strict and accurate. Do not add any text outside the JSON."""


class GradeResult(BaseModel):
    device_type: str
    brand: str
    model: str
    grade: str
    confidence: int
    issues: list[str]
    positives: list[str]
    summary: str
    price_min: int
    price_max: int


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.post("/grade", response_model=GradeResult)
async def grade_device(file: UploadFile = File(...)):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    allowed_types = ["image/jpeg", "image/png", "image/webp", "image/gif"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, WEBP or GIF images are accepted")

    image_data = await file.read()
    if len(image_data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 10MB")

    b64_image = base64.standard_b64encode(image_data).decode("utf-8")
    media_type = file.content_type

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64_image,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Grade this device's physical condition and respond with the JSON only."
                        }
                    ],
                }
            ],
        )
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=f"Claude API error: {str(e)}")

    raw = message.content[0].text.strip()

    # Clean markdown code blocks if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Could not parse model response as JSON")

    grade = data.get("grade", "Used")
    device_type = data.get("device_type", "unknown")
    pricing = PRICING.get(device_type, PRICING["unknown"])
    price_range = pricing.get(grade, pricing["Used"])

    return GradeResult(
        device_type=device_type,
        brand=data.get("brand", "Unknown"),
        model=data.get("model", "Unknown"),
        grade=grade,
        confidence=int(data.get("confidence", 70)),
        issues=data.get("issues", []),
        positives=data.get("positives", []),
        summary=data.get("summary", ""),
        price_min=price_range[0],
        price_max=price_range[1],
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "condition-grader"}
