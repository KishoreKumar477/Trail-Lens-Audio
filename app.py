"""TrailLens Audio — an offline-first trail naturalist companion."""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("traillens")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "kokoro").lower()
KOKORO_VOICE = os.getenv("KOKORO_VOICE", "af_heart")
KOKORO_SPEED = float(os.getenv("KOKORO_SPEED", "0.84"))

PROMPT = """<image>\nTask: Analyze this outdoor trail photograph. You are a cautious naturalist, not a field authority. Identify a plant, tree, insect, fungus, or animal only when its visible features clearly support the answer. NEVER invent a species from weak, distant, blurry, partial, or ambiguous imagery. When uncertain, use an honest broad name such as \"Unconfirmed flowering plant\" and scientific_name \"Unknown\". Never describe a specimen as edible or safe to touch.\nReturn ONLY a valid JSON object matching this schema without markdown fences:\n{\"common_name\": \"<Likely common name, or Unconfirmed [category]>\", \"scientific_name\": \"<Scientific Name or Unknown>\", \"category\": \"<flora | fauna | fungi | other>\", \"identification_confidence\": \"<high | medium | low>\", \"visual_evidence\": \"<Visible feature supporting the identification, max 18 words>\", \"safety_assessment\": \"<safe | toxic to touch | edible | caution>\", \"trail_fact\": \"<One fascinating outdoor ecology fact, max 25 words>\", \"narration_script\": \"<A gentle, unhurried two-sentence naturalist guide. Use warm, simple words with punctuation that creates comfortable pauses. Under 35 words.>\", \"pocket_quest\": \"<A gentle, safe, screen-free 20-second observation prompt. Use a calm, inviting pace. Never ask the user to touch, pick, eat, approach, or disturb wildlife. Under 24 words.>\"}"""

collection: Any = None
ollama_ready = False
kokoro_pipeline: Any = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Connect optional services without preventing a usable offline demo."""
    global collection, ollama_ready
    mongo_uri = os.getenv("MONGO_URI")
    if mongo_uri:
        try:
            from pymongo import MongoClient
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
            client.admin.command("ping")
            collection = client["traillens"]["trail_sightings"]
            logger.info("MongoDB connected")
        except Exception as exc:
            logger.warning("MongoDB unavailable: %s", exc)
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as response:
            models = json.load(response).get("models", [])
        ollama_ready = any(item.get("name") == OLLAMA_MODEL for item in models)
        if ollama_ready:
            logger.info("Local vision model ready through Ollama: %s", OLLAMA_MODEL)
        else:
            logger.warning("Ollama is running, but %s is not installed; using field-note mode", OLLAMA_MODEL)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("Ollama unavailable; using field-note mode: %s", exc)
    yield


app = FastAPI(title="TrailLens Audio", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


def fallback_analysis() -> dict[str, str]:
    return {
        "common_name": "Trail specimen",
        "scientific_name": "Identification needs local model",
        "category": "other",
        "identification_confidence": "low",
        "visual_evidence": "The photo needs a closer, well-lit view for reliable identification.",
        "safety_assessment": "caution",
        "trail_fact": "Every trail-side organism is part of a larger web of soil, sunlight, water, and wildlife.",
        "narration_script": "You have found a trail specimen worth a closer look. Leave it where it grows, and notice its shape, texture, and the life around it.",
        "pocket_quest": "Pocket your phone and find three different textures nearby, without picking or touching anything.",
    }


def clean_analysis(value: dict[str, Any]) -> dict[str, str]:
    fallback = fallback_analysis()
    allowed_categories = {"flora", "fauna", "fungi", "other"}
    allowed_safety = {"safe", "toxic to touch", "edible", "caution"}
    allowed_confidence = {"high", "medium", "low"}
    result = {key: str(value.get(key) or fallback[key]).strip() for key in fallback}
    if result["category"].lower() not in allowed_categories:
        result["category"] = "other"
    if result["safety_assessment"].lower() not in allowed_safety:
        result["safety_assessment"] = "caution"
    if result["identification_confidence"].lower() not in allowed_confidence:
        result["identification_confidence"] = "low"
    if result["identification_confidence"].lower() == "low":
        label = result["category"] if result["category"] != "other" else "trail specimen"
        result["common_name"] = f"Unconfirmed {label}"
        result["scientific_name"] = "Unknown"
        result["safety_assessment"] = "caution"
    return result


def infer(image: Image.Image) -> dict[str, str]:
    """Ask local Ollama Gemma 3 for one strict JSON field observation."""
    if not ollama_ready:
        return fallback_analysis()
    try:
        buffer = io.BytesIO()
        image.thumbnail((896, 896))
        image.save(buffer, format="JPEG", quality=90)
        payload = json.dumps({
            "model": OLLAMA_MODEL,
            "stream": False,
            "format": "json",
            "keep_alive": "10m",
            "options": {"temperature": 0.1},
            "messages": [{"role": "user", "content": PROMPT, "images": [base64.b64encode(buffer.getvalue()).decode("utf-8")]}],
        }).encode("utf-8")
        request = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=180) as response:
            text = json.load(response)["message"]["content"]
        return clean_analysis(json.loads(text))
    except Exception as exc:
        logger.exception("Vision inference failed: %s", exc)
        return fallback_analysis()


def make_kokoro_audio(script: str) -> str:
    """Generate a warm, local WAV narration with the Kokoro neural TTS model."""
    global kokoro_pipeline
    try:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline
        if kokoro_pipeline is None:
            kokoro_pipeline = KPipeline(lang_code="a")
            logger.info("Kokoro local narration model ready: %s", KOKORO_VOICE)
        clips = [np.asarray(audio) for _, _, audio in kokoro_pipeline(script, voice=KOKORO_VOICE, speed=KOKORO_SPEED)]
        if not clips:
            return ""
        audio_buffer = io.BytesIO()
        sf.write(audio_buffer, np.concatenate(clips), 24000, format="WAV")
        return base64.b64encode(audio_buffer.getvalue()).decode("utf-8")
    except Exception as exc:
        logger.warning("Kokoro synthesis failed; using next audio fallback: %s", exc)
        return ""


def make_elevenlabs_audio(script: str) -> str:
    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")
    if not api_key or not voice_id:
        return ""
    try:
        from elevenlabs.client import ElevenLabs
        audio = ElevenLabs(api_key=api_key).text_to_speech.convert(
            voice_id=voice_id, model_id="eleven_multilingual_v2", text=script,
        )
        return base64.b64encode(b"".join(audio)).decode("utf-8")
    except Exception as exc:
        logger.warning("ElevenLabs synthesis failed: %s", exc)
        return ""


def make_audio(script: str) -> tuple[str, str]:
    """Prefer local neural narration, then optional ElevenLabs, then browser speech."""
    if TTS_PROVIDER in {"kokoro", "auto"}:
        audio = make_kokoro_audio(script)
        if audio:
            return audio, "wav"
    if TTS_PROVIDER in {"elevenlabs", "auto"}:
        audio = make_elevenlabs_audio(script)
        if audio:
            return audio, "mpeg"
    return "", ""


@app.get("/", include_in_schema=False)
async def home() -> FileResponse:
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"status": "ready", "local_vision": ollama_ready, "model": OLLAMA_MODEL, "tts_provider": TTS_PROVIDER, "database": collection is not None}


@app.post("/api/identify")
async def identify(file: UploadFile = File(...), lat: float = Form(0), lng: float = Form(0), trail_name: str = Form("")) -> dict[str, Any]:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload a photo.")
    try:
        image = Image.open(io.BytesIO(await file.read())).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="That image could not be read.") from exc
    analysis = infer(image)
    record = {**analysis, "location": {"lat": lat, "lng": lng, "trail_name": trail_name.strip()}, "created_at": datetime.now(timezone.utc)}
    sighting_id = ""
    if collection is not None:
        try:
            sighting_id = str(collection.insert_one(record).inserted_id)
        except Exception as exc:
            logger.warning("Could not save sighting: %s", exc)
    guide_audio, audio_format = make_audio(analysis["narration_script"])
    quest_audio, quest_audio_format = make_audio(analysis["pocket_quest"])
    return {
        "analysis": analysis,
        "audio_base64": guide_audio,
        "audio_format": audio_format,
        "quest_audio_base64": quest_audio,
        "quest_audio_format": quest_audio_format,
        "sighting_id": sighting_id,
        "mode": "local AI" if ollama_ready else "field-note demo",
    }
