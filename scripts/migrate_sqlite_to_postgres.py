from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


TABLE_COLUMNS = {
    "book_metadata": [
        "isbn",
        "title",
        "subtitle",
        "authors",
        "publisher",
        "published_date",
        "format",
        "series",
        "series_number",
        "description",
        "thumbnail_url",
        "source",
        "retrieved_at",
    ],
    "cache_stats": [
        "id",
        "hits",
        "misses",
        "stale",
    ],
}


def read_sqlite_rows(
    sqlite_path: Path,
    table: str,
) -> list[dict]:
    with sqlite3.connect(sqlite_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"SELECT * FROM {table}"
        ).fetchall()

    return [dict(row) for row in rows]


def ensure_destination_schema(engine) -> None:
    # Importing the application cache module creates the SQLAlchemy
    # table definitions and calls create_all() against DATABASE_URL.
    from bibliography.cache import MetadataCache

    MetadataCache()


def destination_count(engine, table: str) -> int:
    with engine.connect() as connection:
        return connection.execute(
            text(f"SELECT COUNT(*) FROM {table}")
        ).scalar_one()


def clear_destination(engine, table: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(f"DELETE FROM {table}")
        )


def insert_rows(
    engine,
    table: str,
    rows: list[dict],
) -> None:
    if not rows:
        return

    columns = TABLE_COLUMNS[table]
    column_sql = ", ".join(columns)
    value_sql = ", ".join(
        f":{column}"
        for column in columns
    )

    statement = text(
        f"""
        INSERT INTO {table} ({column_sql})
        VALUES ({value_sql})
        """
    )

    prepared = []

    for row in rows:
        prepared.append(
            {
                column: row.get(column)
                for column in columns
            }
        )

    with engine.begin() as connection:
        connection.execute(
            statement,
            prepared,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Copy Book Sourcing metadata from SQLite "
            "to the configured PostgreSQL DATABASE_URL."
        )
    )

    parser.add_argument(
        "--sqlite",
        default="data/metadata.db",
        help="Path to the existing SQLite metadata database.",
    )

    parser.add_argument(
        "--replace",
        action="store_true",
        help=(
            "Clear destination tables before copying. "
            "Use only for an empty/test PostgreSQL database."
        ),
    )

    args = parser.parse_args()

    sqlite_path = Path(args.sqlite).expanduser().resolve()

    if not sqlite_path.exists():
        raise SystemExit(
            f"SQLite database not found: {sqlite_path}"
        )

    from core.config import settings

    if not settings.database_url.startswith(
        ("postgresql://", "postgresql+psycopg://")
    ):
        raise SystemExit(
            "DATABASE_URL is not PostgreSQL. "
            "Set it before running this migration."
        )

    engine = create_engine(
        settings.database_url,
        future=True,
        pool_pre_ping=True,
    )

    print("Source SQLite:", sqlite_path)
    print("Destination:", engine.url.render_as_string(
        hide_password=True
    ))

    ensure_destination_schema(engine)

    inspector = inspect(engine)

    for table in TABLE_COLUMNS:
        if table not in inspector.get_table_names():
            raise SystemExit(
                f"Destination table was not created: {table}"
            )

    source = {
        table: read_sqlite_rows(
            sqlite_path,
            table,
        )
        for table in TABLE_COLUMNS
    }

    print()
    print("Source rows:")
    for table, rows in source.items():
        print(f"  {table}: {len(rows)}")

    existing = {
        table: destination_count(
            engine,
            table,
        )
        for table in TABLE_COLUMNS
    }

    print()
    print("Destination rows before migration:")
    for table, count in existing.items():
        print(f"  {table}: {count}")

    if any(existing.values()) and not args.replace:
        raise SystemExit(
            "\nDestination is not empty. "
            "Nothing was changed. Re-run with --replace only "
            "if this is the correct test database."
        )

    if args.replace:
        # Delete child/non-essential table first; there are currently
        # no foreign keys, but keeping the order explicit is safer.
        clear_destination(engine, "book_metadata")
        clear_destination(engine, "cache_stats")

    insert_rows(
        engine,
        "book_metadata",
        source["book_metadata"],
    )

    # The cache module creates id=1 automatically, so replace that
    # single row rather than attempting a duplicate insert.
    if source["cache_stats"]:
        clear_destination(
            engine,
            "cache_stats",
        )
        insert_rows(
            engine,
            "cache_stats",
            source["cache_stats"],
        )

    final = {
        table: destination_count(
            engine,
            table,
        )
        for table in TABLE_COLUMNS
    }

    print()
    print("Destination rows after migration:")
    for table, count in final.items():
        print(f"  {table}: {count}")

    if final["book_metadata"] != len(
        source["book_metadata"]
    ):
        raise SystemExit(
            "Verification failed: book_metadata row count differs."
        )

    if source["cache_stats"]:
        if final["cache_stats"] != len(
            source["cache_stats"]
        ):
            raise SystemExit(
                "Verification failed: cache_stats row count differs."
            )

    print()
    print("Migration completed and row counts verified.")
    print("The original SQLite database was not modified.")


if __name__ == "__main__":
    main()
