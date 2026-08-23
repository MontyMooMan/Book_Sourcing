import requests

from bibliography.models import BookMetadata


class OpenLibraryProvider:
    name = "Open Library"

    endpoint = (
        "https://openlibrary.org/api/books"
    )

    edition_endpoint = (
        "https://openlibrary.org/isbn/{isbn}.json"
    )

    @staticmethod
    def _first_text(
        value,
    ) -> str:

        if isinstance(
            value,
            str,
        ):
            return value.strip()

        if isinstance(
            value,
            list,
        ):
            for item in value:
                text = str(
                    item
                ).strip()

                if text:
                    return text

        return ""

    def _lookup_edition(
        self,
        isbn: str,
    ) -> dict:

        try:
            response = requests.get(
                self.edition_endpoint.format(
                    isbn=isbn
                ),
                timeout=15,
            )

            response.raise_for_status()

        except requests.RequestException as exc:
            print(
                f"{self.name} edition request failed: "
                f"{exc}"
            )
            return {}

        try:
            return response.json()

        except ValueError:
            print(
                f"{self.name}: invalid edition JSON response"
            )
            return {}

    def lookup(
        self,
        isbn: str,
    ) -> BookMetadata | None:

        bibkey = f"ISBN:{isbn}"

        try:
            response = requests.get(
                self.endpoint,
                params={
                    "bibkeys": bibkey,
                    "format": "json",
                    "jscmd": "data",
                },
                timeout=15,
            )

            response.raise_for_status()

        except requests.RequestException as exc:
            print(
                f"{self.name} request failed: {exc}"
            )
            return None

        try:
            data = response.json()

        except ValueError:
            print(
                f"{self.name}: invalid JSON response"
            )
            return None

        book = data.get(
            bibkey
        )

        if not book:
            return None

        edition = self._lookup_edition(
            isbn
        )

        authors = [
            author.get(
                "name",
                "",
            )
            for author in book.get(
                "authors",
                [],
            )
            if author.get("name")
        ]

        publishers = [
            publisher.get(
                "name",
                "",
            )
            for publisher in book.get(
                "publishers",
                [],
            )
            if publisher.get("name")
        ]

        if not publishers:
            publishers = [
                str(publisher).strip()
                for publisher in edition.get(
                    "publishers",
                    [],
                )
                if str(publisher).strip()
            ]

        cover = book.get(
            "cover",
            {},
        )

        book_format = (
            self._first_text(
                book.get(
                    "physical_format",
                    "",
                )
            )
            or self._first_text(
                edition.get(
                    "physical_format",
                    "",
                )
            )
        )

        series = (
            self._first_text(
                book.get(
                    "series",
                    "",
                )
            )
            or self._first_text(
                edition.get(
                    "series",
                    "",
                )
            )
        )

        series_number = (
            self._first_text(
                book.get(
                    "series_number",
                    "",
                )
            )
            or self._first_text(
                edition.get(
                    "series_number",
                    "",
                )
            )
        )

        return BookMetadata(
            isbn=isbn,
            title=book.get(
                "title",
                "",
            ),
            authors=authors,
            publisher=(
                publishers[0]
                if publishers
                else ""
            ),
            published_date=(
                book.get(
                    "publish_date",
                    "",
                )
                or edition.get(
                    "publish_date",
                    "",
                )
            ),
            format=book_format,
            series=series,
            series_number=series_number,
            thumbnail_url=(
                cover.get(
                    "medium",
                    "",
                )
                or cover.get(
                    "small",
                    "",
                )
            ),
            source=self.name,
        )
