from dataclasses import dataclass, field


@dataclass
class BookMetadata:
    isbn: str

    title: str = ""
    subtitle: str = ""

    authors: list[str] = field(
        default_factory=list
    )

    publisher: str = ""
    published_date: str = ""
    format: str = ""

    series: str = ""
    series_number: str = ""

    description: str = ""
    thumbnail_url: str = ""

    source: str = ""
