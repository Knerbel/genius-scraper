import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    genius_access_token: str
    database_url: str
    request_delay: float


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        genius_access_token=os.getenv("GENIUS_ACCESS_TOKEN", ""),
        database_url=os.getenv("DATABASE_URL", "sqlite:///genius.db"),
        request_delay=float(os.getenv("REQUEST_DELAY", "0.5")),
    )
