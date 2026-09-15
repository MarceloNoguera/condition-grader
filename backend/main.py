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
app.mount("/static", StaticFiles(directory="docs"), name="static")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Indicative ranges per device class and grade. They deliberately ignore brand and
# model, so a flagship and a budget handset of the same class price identically —
# the device-pricing project replaces this table with a model fitted on sold
# listings. Until then, keeping a class here is still far better than letting it
# fall through to "other", which is what priced a Canon EOS M50 at 100-200.
PRICING = {
    "smartphone": {"Flawless": (250, 320), "Good": (150, 220), "Used": (60, 130),  "Damaged": (10, 50)},
    "laptop":     {"Flawless": (500, 700), "Good": (300, 480), "Used": (150, 280), "Damaged": (30, 100)},
    "tablet":     {"Flawless": (200, 300), "Good": (120, 190), "Used": (50, 110),  "Damaged": (10, 40)},
    "camera":     {"Flawless": (300, 550), "Good": (200, 380), "Used": (100, 220), "Damaged": (30, 90)},
    "smartwatch": {"Flawless": (120, 220), "Good": (70, 140),  "Used": (30, 80),   "Damaged": (10, 30)},
    "console":    {"Flawless": (200, 350), "Good": (140, 240), "Used": (70, 150),  "Damaged": (20, 60)},
    "headphones": {"Flawless": (80, 180),  "Good": (50, 110),  "Used": (20, 60),   "Damaged": (5, 25)},
    "monitor":    {"Flawless": (90, 200),  "Good": (60, 130),  "Used": (25, 70),   "Damaged": (10, 30)},
    "other":      {"Flawless": (100, 200), "Good": (60, 120),  "Used": (20, 60),   "Damaged": (5, 20)},
}

DEVICE_TYPES = [t for t in PRICING if t != "other"]

SYSTEM_PROMPT = f"""You are an expert electronics grader for a trade-in platform.
Analyze the provided image of a used electronic device and grade its physical condition.

Respond ONLY with a valid JSON object with these exact fields:
{{
  "device_type": "{' | '.join(DEVICE_TYPES)} | other",
  "brand": "detected brand or Unknown",
  "model": "detected model or Unknown",
  "grade": "Flawless | Good | Used | Damaged",
  "confidence": <integer 0-100>,
  "issues": ["list of detected physical issues, empty array if none"],
  "positives": ["list of positive condition notes"],
  "summary": "One sentence summary of the device condition"
}}

Use "other" for device_type only when the item genuinely does not fit any listed class.

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
    return FileResponse("docs/index.html")


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
    device_type = data.get("device_type", "other")
    pricing = PRICING.get(device_type, PRICING["other"])
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
