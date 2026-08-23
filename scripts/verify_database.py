from __future__ import annotations

from sqlalchemy import inspect, text

from core.database import engine


def main() -> None:
    print(
        "Database:",
        engine.url.render_as_string(
            hide_password=True
        ),
    )

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    print("Tables:", ", ".join(tables) or "(none)")

    with engine.connect() as connection:
        for table in (
            "book_metadata",
            "cache_stats",
        ):
            if table not in tables:
                print(f"{table}: missing")
                continue

            count = connection.execute(
                text(
                    f"SELECT COUNT(*) "
                    f"FROM {table}"
                )
            ).scalar_one()

            print(f"{table}: {count} rows")


if __name__ == "__main__":
    main()
