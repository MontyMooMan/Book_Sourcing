from __future__ import annotations

import json

from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    insert,
    select,
    update,
)

from bibliography.models import BookMetadata
from core.config import settings
from core.database import engine


metadata = MetaData()

book_metadata = Table(
    "book_metadata",
    metadata,
    Column("isbn", String(32), primary_key=True),
    Column("title", Text, nullable=False),
    Column("subtitle", Text),
    Column("authors", Text),
    Column("publisher", Text),
    Column("published_date", String(64)),
    Column("format", String(128)),
    Column("series", Text),
    Column("series_number", String(64)),
    Column("description", Text),
    Column("thumbnail_url", Text),
    Column("source", Text),
    Column("retrieved_at", String(64), nullable=False),
)

cache_stats = Table(
    "cache_stats",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("hits", Integer, nullable=False, default=0),
    Column("misses", Integer, nullable=False, default=0),
    Column("stale", Integer, nullable=False, default=0),
)


class MetadataCache:
    def __init__(
        self,
        max_age_days: int | None = None,
    ):
        if max_age_days is None:
            max_age_days = (
                settings.metadata_cache_max_age_days
            )

        self.max_age = timedelta(
            days=max_age_days
        )

        self._create_tables()

    def _create_tables(self) -> None:
        metadata.create_all(engine)

        with engine.begin() as connection:
            existing = connection.execute(
                select(cache_stats.c.id)
                .where(cache_stats.c.id == 1)
            ).first()

            if existing is None:
                connection.execute(
                    insert(cache_stats).values(
                        id=1,
                        hits=0,
                        misses=0,
                        stale=0,
                    )
                )

    def _increment_stat(
        self,
        column_name: str,
        also_miss: bool = False,
    ) -> None:
        values = {
            column_name:
                getattr(cache_stats.c, column_name) + 1
        }

        if also_miss:
            values["misses"] = (
                cache_stats.c.misses + 1
            )

        with engine.begin() as connection:
            connection.execute(
                update(cache_stats)
                .where(cache_stats.c.id == 1)
                .values(**values)
            )

    def _record_hit(self) -> None:
        self._increment_stat("hits")

    def _record_miss(self) -> None:
        self._increment_stat("misses")

    def _record_stale(self) -> None:
        self._increment_stat(
            "stale",
            also_miss=True,
        )

    def get(
        self,
        isbn: str,
    ) -> BookMetadata | None:
        with engine.connect() as connection:
            row = connection.execute(
                select(book_metadata)
                .where(book_metadata.c.isbn == isbn)
            ).mappings().first()

        if row is None:
            self._record_miss()
            return None

        try:
            retrieved_at = datetime.fromisoformat(
                row["retrieved_at"]
            )
        except (TypeError, ValueError):
            self._record_stale()
            return None

        if retrieved_at.tzinfo is None:
            retrieved_at = retrieved_at.replace(
                tzinfo=timezone.utc
            )

        if (
            datetime.now(timezone.utc)
            - retrieved_at
            > self.max_age
        ):
            self._record_stale()
            return None

        self._record_hit()

        try:
            authors = json.loads(
                row["authors"] or "[]"
            )
        except json.JSONDecodeError:
            authors = []

        return BookMetadata(
            isbn=row["isbn"],
            title=row["title"] or "",
            subtitle=row["subtitle"] or "",
            authors=authors,
            publisher=row["publisher"] or "",
            published_date=row["published_date"] or "",
            format=row["format"] or "",
            series=row["series"] or "",
            series_number=row["series_number"] or "",
            description=row["description"] or "",
            thumbnail_url=row["thumbnail_url"] or "",
            source=row["source"] or "",
        )

    def save(
        self,
        metadata_record: BookMetadata,
    ) -> None:
        values = {
            "isbn": metadata_record.isbn,
            "title": metadata_record.title,
            "subtitle": metadata_record.subtitle,
            "authors": json.dumps(
                metadata_record.authors
            ),
            "publisher": metadata_record.publisher,
            "published_date":
                metadata_record.published_date,
            "format": metadata_record.format,
            "series": metadata_record.series,
            "series_number":
                metadata_record.series_number,
            "description":
                metadata_record.description,
            "thumbnail_url":
                metadata_record.thumbnail_url,
            "source": metadata_record.source,
            "retrieved_at":
                datetime.now(timezone.utc).isoformat(),
        }

        with engine.begin() as connection:
            existing = connection.execute(
                select(book_metadata.c.isbn)
                .where(
                    book_metadata.c.isbn
                    == metadata_record.isbn
                )
            ).first()

            if existing is None:
                connection.execute(
                    insert(book_metadata)
                    .values(**values)
                )
            else:
                connection.execute(
                    update(book_metadata)
                    .where(
                        book_metadata.c.isbn
                        == metadata_record.isbn
                    )
                    .values(**values)
                )
