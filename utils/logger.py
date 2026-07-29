import os
import json
import logging
from datetime import datetime
from config import Config
from models import DebateLog


def setup_logging():
    """Configures standard logging formatting."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )


def save_debate_log(debate_log: DebateLog) -> str:
    """
    Saves structured DebateLog object as a JSON file in Config.LOG_DIR.
    Returns path to the saved file.
    """
    os.makedirs(Config.LOG_DIR, exist_ok=True)
    
    timestamp_slug = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"debate_{timestamp_slug}.json"
    filepath = os.path.join(Config.LOG_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(debate_log.to_dict(), f, indent=2, ensure_ascii=False)

    return filepath
