# Device Condition Grader

AI-powered trade-in grading system for used electronics using Claude Vision (claude-opus-4-5).

Upload a photo of any smartphone, laptop, or tablet and receive:
- **Physical condition grade**: Flawless / Good / Used / Damaged
- **Confidence score**
- **Detected issues and positives**
- **Estimated trade-in price range**

## Tech Stack

- **Backend**: FastAPI + Anthropic Claude Vision (multimodal LLM)
- **Frontend**: Vanilla HTML/CSS/JS (single file, no build step)
- **Serving**: Uvicorn + Docker

## Quick Start

### With Docker (recommended)

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

docker compose up --build
```

Open http://localhost:8000

### Without Docker

```bash
cd backend
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn main:app --reload
```

Open http://localhost:8000

## API

### POST /grade

Accepts a multipart image upload, returns JSON:

```json
{
  "device_type": "smartphone",
  "brand": "Apple",
  "model": "iPhone 14",
  "grade": "Good",
  "confidence": 88,
  "issues": ["Light scratch on bottom-left corner of screen"],
  "positives": ["No cracks", "Clean back panel", "Ports look intact"],
  "summary": "iPhone in good condition with minor cosmetic wear.",
  "price_min": 150,
  "price_max": 220
}
```

### GET /health

Returns `{"status": "ok"}` — for container health checks.

## Project Structure

```
condition-grader/
├── backend/
│   ├── main.py          # FastAPI app + Claude Vision integration
│   └── requirements.txt
├── docs/
│   └── index.html       # Frontend (served by FastAPI, and by GitHub Pages)
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## Deployment

- **Backend**: deployed on [Railway](https://railway.app) from the `Dockerfile`, at
  `https://condition-grader-production.up.railway.app`.
- **Frontend**: `docs/index.html` is also published via GitHub Pages (repo Settings →
  Pages → source: `main` branch, `/docs` folder). It calls the Railway backend directly
  (see `API_BASE` at the top of the `<script>` block).
