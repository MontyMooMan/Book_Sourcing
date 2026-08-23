from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from core.config import settings


def create_database_engine() -> Engine:
    connect_args = {}

    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(
        settings.database_url,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


engine = create_database_engine()
