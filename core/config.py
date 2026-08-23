from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Load local development variables from <project>/.env when present.
# Hosting platforms can still provide real environment variables directly.
load_dotenv(
    PROJECT_ROOT / ".env",
    override=False,
)


def _env_bool(
    name: str,
    default: bool,
) -> bool:
    raw = os.getenv(name)

    if raw is None:
        return default

    return raw.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _env_int(
    name: str,
    default: int,
) -> int:
    raw = os.getenv(name)

    if raw is None:
        return default

    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    environment: str
    debug: bool

    google_books_api_key: str

    database_url: str
    metadata_database_path: Path
    metadata_cache_max_age_days: int

    enable_live_suppliers: bool

    app_title: str
    app_version: str


def load_settings() -> Settings:
    environment = os.getenv(
        "APP_ENV",
        "development",
    ).strip().lower()

    debug_default = (
        environment == "development"
    )

    live_suppliers_default = (
        environment == "development"
    )

    database_value = os.getenv(
        "METADATA_DATABASE_PATH",
        str(
            PROJECT_ROOT
            / "data"
            / "metadata.db"
        ),
    )

    return Settings(
        environment=environment,
        debug=_env_bool(
            "APP_DEBUG",
            debug_default,
        ),
        google_books_api_key=os.getenv(
            "GOOGLE_BOOKS_API_KEY",
            "",
        ).strip(),
        database_url=os.getenv(
            "DATABASE_URL",
            (
                "sqlite:///"
                + str(Path(database_value).expanduser())
            ),
        ).strip(),
        metadata_database_path=Path(
            database_value
        ).expanduser(),
        metadata_cache_max_age_days=_env_int(
            "METADATA_CACHE_MAX_AGE_DAYS",
            365,
        ),
        enable_live_suppliers=_env_bool(
            "ENABLE_LIVE_SUPPLIERS",
            live_suppliers_default,
        ),
        app_title=os.getenv(
            "APP_TITLE",
            "Book Sourcing",
        ).strip(),
        app_version=os.getenv(
            "APP_VERSION",
            "0.1.0",
        ).strip(),
    )


settings = load_settings()
