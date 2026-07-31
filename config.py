import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    DEFAULT_REBUTTAL_ROUNDS = int(os.getenv("DEFAULT_REBUTTAL_ROUNDS", "2"))
    LOG_DIR = os.getenv("LOG_DIR", "logs")

    @classmethod
    def validate(cls):
        if not cls.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY environment variable is required. Please check your .env file.")
