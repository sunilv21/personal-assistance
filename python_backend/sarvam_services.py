import httpx
import base64
import time
from .config import settings

# ── Persistent HTTP client with connection pooling (reuses TCP connections) ──
_client = httpx.Client(timeout=20, limits=httpx.Limits(max_connections=10, max_keepalive_connections=5))

HEADERS = {
    "api-subscription-key": settings.SARVAM_API_KEY,
}

# ============================================================
#  SPEECH-TO-TEXT  (Saaras v3)
#  Sarvam accepts webm natively — NO ffmpeg needed!
# ============================================================
def sarvam_stt(audio_bytes: bytes, filename: str = "audio.wav", language: str | None = None):
    t0 = time.time()
    url = f"{settings.SARVAM_BASE_URL}/speech-to-text"

    # Detect content type — Sarvam supports webm, mp3, wav, etc. directly
    if filename.endswith(".webm"):
        content_type = "audio/webm"
    elif filename.endswith(".mp4"):
        content_type = "audio/mp4"
    elif filename.endswith(".ogg"):
        content_type = "audio/ogg"
    else:
        content_type = "audio/wav"

    files = {
        "file": (filename, audio_bytes, content_type),
    }
    lang_code = language if language else "unknown"
    if lang_code != "unknown" and "-" not in lang_code:
        lang_code = f"{lang_code}-IN"
    data = {
        "model": settings.SARVAM_STT_MODEL,
        "language_code": lang_code,
    }

    try:
        response = _client.post(url, headers=HEADERS, files=files, data=data)
        dt = time.time() - t0

        print(f"[STT] {response.status_code} in {dt:.2f}s | {response.text[:200]}")

        if response.status_code != 200:
            return None, settings.SARVAM_DEFAULT_LANGUAGE, 0.0

        result = response.json()
        transcript = result.get("transcript", "").strip()
        language   = result.get("language_code", settings.SARVAM_DEFAULT_LANGUAGE)
        confidence = result.get("language_probability", 0.0)

        if not transcript:
            return None, language, 0.0
        return transcript, language, confidence if confidence else 0.9

    except Exception as e:
        print(f"[STT] Error: {e}")
        return None, settings.SARVAM_DEFAULT_LANGUAGE, 0.0


# ============================================================
#  TEXT-TO-SPEECH  (Bulbul v3)
# ============================================================
def sarvam_tts(text: str, language: str, voice: str | None = None) -> bytes:
    t0 = time.time()
    url = f"{settings.SARVAM_BASE_URL}/text-to-speech"

    if language and "-" not in language:
        language = f"{language}-IN"

    speaker = (voice or settings.SARVAM_TTS_SPEAKER or "shubh").strip().lower()

    payload = {
        "text": text,
        "target_language_code": language or settings.SARVAM_DEFAULT_LANGUAGE,
        "model": settings.SARVAM_TTS_MODEL,
        "speaker": speaker,
        "output_audio_codec": "wav",          # uncompressed PCM — no MP3 codec artifacts
        "speech_sample_rate": "24000",        # 24kHz = noticeably cleaner than 22050
        "enable_preprocessing": True,
    }

    try:
        response = _client.post(url, headers={**HEADERS, "Content-Type": "application/json"}, json=payload)
        dt = time.time() - t0

        print(f"[TTS] {response.status_code} in {dt:.2f}s | {response.text[:120]}")

        if response.status_code != 200:
            return b""

        audios = response.json().get("audios", [])
        if not audios:
            return b""

        return base64.b64decode(audios[0])

    except Exception as e:
        print(f"[TTS] Error: {e}")
        return b""
