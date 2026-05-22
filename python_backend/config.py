import os
from dotenv import load_dotenv, find_dotenv

# Walks up the directory tree from this file to find .env — so it works
# whether you run from the project root or from python_backend/.
load_dotenv(find_dotenv(usecwd=True), override=True)

class Settings:
    SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
    SARVAM_BASE_URL = os.getenv("SARVAM_BASE_URL", "https://api.sarvam.ai")
    SARVAM_STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v3")
    SARVAM_TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
    SARVAM_TTS_SPEAKER = os.getenv("SARVAM_TTS_SPEAKER", "Shubh")
    SARVAM_DEFAULT_LANGUAGE = os.getenv("SARVAM_DEFAULT_LANGUAGE", "mr-IN")

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-nano")
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 0.5))
    LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", 500))

    CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", 0.3))
    DEFAULT_FALLBACK_LANGUAGE = os.getenv("DEFAULT_FALLBACK_LANGUAGE", "mr-IN")
    MAX_CONTEXT_MESSAGES = int(os.getenv("MAX_CONTEXT_MESSAGES", 5))

settings = Settings()
