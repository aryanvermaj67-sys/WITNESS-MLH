"""Typed settings from backend/.env (REQUIREMENTS.md §6)."""
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, SecretStr

BACKEND = Path(__file__).resolve().parent.parent

load_dotenv(BACKEND / ".env")


class Settings(BaseModel):
    GEMINI_API_KEY: SecretStr = SecretStr("")  # SecretStr so the key never shows up in a print or log
    GEMINI_MODEL: str = "gemma-4-26b-a4b-it"
    LMSTUDIO_BASE_URL: str = "http://localhost:1234/v1"
    LMSTUDIO_MODEL: str = ""
    NLI_MODEL: str = "cross-encoder/nli-deberta-v3-small"
    EMBED_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    NLI_DEVICE: str = "cpu"
    KB_DIR: str = "data/handbook"
    CACHE_DIR: str = "data/cached"
    FRONTEND_DIST: str = "../frontend/dist"
    TOP_K: int = 5
    RRF_K: int = 60
    NLI_ENTAIL_THRESHOLD: float = 0.70
    NLI_CONTRA_THRESHOLD: float = 0.70
    NLI_RELATED_K: int = 3  # a contradiction only counts from the K sentences most similar to the claim...
    NLI_RELATED_MIN_SIM: float = 0.55  # ...and only if their MiniLM cosine similarity is at least this
    GEN_TEMPERATURE: float = 0.0
    GEN_MAX_TOKENS: int = 200
    OFFLINE_REPLAY: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    def path(self, value: str) -> Path:
        """Resolve a directory setting relative to backend/."""
        return (BACKEND / value).resolve()


settings = Settings(**{name: os.environ[name] for name in Settings.model_fields if os.environ.get(name)})
