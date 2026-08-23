import sqlite3
from pathlib import Path


DATABASE_PATH = Path(
    "data/metadata.db"
)


def format_size(
    size_bytes: int,
) -> str:

    if size_bytes < 1024:
        return f"{size_bytes} B"

    if size_bytes < 1024 ** 2:
        return (
            f"{size_bytes / 1024:.1f} KB"
        )

    if size_bytes < 1024 ** 3:
        return (
            f"{size_bytes / (1024 ** 2):.1f} MB"
        )

    return (
        f"{size_bytes / (1024 ** 3):.2f} GB"
    )


def main():

    if not DATABASE_PATH.exists():
        print(
            "Metadata cache does not exist yet."
        )
        return

    file_size = (
        DATABASE_PATH
        .stat()
        .st_size
    )

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    try:
        total = connection.execute(
            """
            SELECT COUNT(*)
            FROM book_metadata
            """
        ).fetchone()[0]

        oldest = connection.execute(
            """
            SELECT MIN(retrieved_at)
            FROM book_metadata
            """
        ).fetchone()[0]

        newest = connection.execute(
            """
            SELECT MAX(retrieved_at)
            FROM book_metadata
            """
        ).fetchone()[0]

        sources = connection.execute(
            """
            SELECT
                source,
                COUNT(*)
            FROM book_metadata
            GROUP BY source
            ORDER BY COUNT(*) DESC
            """
        ).fetchall()

        stats = connection.execute(
            """
            SELECT
                hits,
                misses,
                stale
            FROM cache_stats
            WHERE id = 1
            """
        ).fetchone()

    finally:
        connection.close()

    hits = 0
    misses = 0
    stale = 0

    if stats:
        hits = stats[0]
        misses = stats[1]
        stale = stats[2]

    lookups = (
        hits
        + misses
    )

    hit_rate = 0

    if lookups:
        hit_rate = (
            hits
            / lookups
            * 100
        )

    print()
    print("=" * 60)
    print("Metadata Cache")
    print("=" * 60)

    print(
        f"Database: {DATABASE_PATH}"
    )

    print(
        f"File size: {format_size(file_size)}"
    )

    print(
        f"Cached ISBNs: {total:,}"
    )

    print(
        f"Oldest record: {oldest or '-'}"
    )

    print(
        f"Newest record: {newest or '-'}"
    )

    print()

    print("Cache performance:")

    print(
        f"  Lookups: {lookups:,}"
    )

    print(
        f"  Hits: {hits:,}"
    )

    print(
        f"  Misses: {misses:,}"
    )

    print(
        f"  Stale records: {stale:,}"
    )

    print(
        f"  Hit rate: {hit_rate:.1f}%"
    )

    print()

    print("Sources:")

    if not sources:
        print(
            "  No cached records."
        )

    else:
        for source, count in sources:
            print(
                f"  {source or 'Unknown'}: "
                f"{count:,}"
            )


if __name__ == "__main__":
    main()
