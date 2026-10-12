# TrailLens Audio 🌿

An offline-first naturalist companion for Hacktoberfest's **Touch Grass** challenge. Take one photo; TrailLens identifies the specimen, records the observation, and narrates a short guide so the hiker can put the screen away.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Open `http://localhost:8000`. It starts in **field-note demo mode** with no accounts, model download, or connectivity required. Browser speech supplies narration when ElevenLabs is not configured.

## Use the local Gemma vision model

Install [Ollama](https://ollama.com), then download the quantized vision model once:

```bash
ollama pull gemma3:4b
```

Copy `.env.example` to `.env`. TrailLens will connect to Ollama at `http://127.0.0.1:11434` and send photos only to your local Gemma 3 model. Optional integrations degrade safely:

| Service | Purpose | Required setting |
|---|---|---|
| Ollama + Gemma 3 4B | Quantized local visual identification | `OLLAMA_MODEL=gemma3:4b` |
| Kokoro 82M | Free local neural narration | `TTS_PROVIDER=kokoro` |
| ElevenLabs | Naturalist narration | `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` |
| MongoDB Atlas | Sighting history and location | `MONGO_URI` |

## Deploy on Render

Create a Web Service from this repository, select **Docker**, and add the same environment variables in Render's dashboard. Render provides `PORT` automatically. A Render service cannot access Ollama running on your Mac, so it will run in safe demo mode unless you deploy an Ollama-compatible inference service alongside it.

### Local neural narration

Kokoro is the default narrator and currently requires Python 3.12 or earlier (it does not yet support Python 3.13). On macOS, create a dedicated compatible environment, install its English pronunciation helper, then refresh dependencies:

```bash
brew install espeak-ng
brew install python@3.12
python3.12 -m venv .venv-kokoro
source .venv-kokoro/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Its first narration downloads the small Kokoro voice model; later narration is local. Set `TTS_PROVIDER=elevenlabs` if you prefer a configured paid ElevenLabs voice instead.

## Safety

TrailLens is educational, not a field authority. It never treats AI output as confirmation that a specimen is edible or safe to touch. Do not consume, handle, or disturb wildlife based on an identification.
