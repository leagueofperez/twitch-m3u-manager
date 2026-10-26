import os


class Config:
    DEBUG = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 16 * 1024))
    PUBLIC_URL = os.environ.get("PUBLIC_URL", "").strip()
