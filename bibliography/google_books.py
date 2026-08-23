import os

import requests

from bibliography.models import BookMetadata


class GoogleBooksProvider:
    name = "Google Books"

    endpoint = (
        "https://www.googleapis.com/books/v1/volumes"
    )

    series_endpoint = (
        "https://www.googleapis.com/books/v1/series/get"
    )

    def __init__(self):
        self.api_key = os.getenv(
            "GOOGLE_BOOKS_API_KEY"
        )

    def _key_params(self) -> dict:
        if self.api_key:
            return {
                "key": self.api_key,
            }

        return {}

    def _get_full_volume(
        self,
        volume_id: str,
    ) -> dict | None:

        if not volume_id:
            return None

        params = {
            "projection": "full",
            "includeNonComicsSeries": "true",
            **self._key_params(),
        }

        try:
            response = requests.get(
                f"{self.endpoint}/{volume_id}",
                params=params,
                timeout=15,
            )

            response.raise_for_status()

        except requests.RequestException as exc:
            print(
                f"{self.name}: full volume request failed: "
                f"{exc}"
            )
            return None

        try:
            return response.json()

        except ValueError:
            print(
                f"{self.name}: invalid full-volume JSON response"
            )
            return None

    def _get_series_title(
        self,
        series_id: str,
    ) -> str:

        if not series_id:
            return ""

        params = {
            "series_id": series_id,
            **self._key_params(),
        }

        try:
            response = requests.get(
                self.series_endpoint,
                params=params,
                timeout=15,
            )

            response.raise_for_status()

        except requests.RequestException as exc:
            print(
                f"{self.name}: series request failed: "
                f"{exc}"
            )
            return ""

        try:
            data = response.json()

        except ValueError:
            print(
                f"{self.name}: invalid series JSON response"
            )
            return ""

        series_items = data.get(
            "series",
            [],
        )

        if not series_items:
            return ""

        return str(
            series_items[0].get(
                "title",
                "",
            )
            or ""
        ).strip()

    @staticmethod
    def _series_details(
        volume: dict,
    ) -> tuple[str, str]:

        series_info = volume.get(
            "seriesInfo",
            {},
        ) or {}

        display_number = str(
            series_info.get(
                "bookDisplayNumber",
                "",
            )
            or ""
        ).strip()

        series_id = ""
        order_number = ""

        volume_series = series_info.get(
            "volumeSeries",
            [],
        ) or []

        if volume_series:
            first_series = volume_series[0]

            series_id = str(
                first_series.get(
                    "seriesId",
                    "",
                )
                or ""
            ).strip()

            raw_order = first_series.get(
                "orderNumber"
            )

            if raw_order is not None:
                order_number = str(
                    raw_order
                ).strip()

        series_number = (
            order_number
            or display_number
        )

        return (
            series_id,
            series_number,
        )

    def lookup(
        self,
        isbn: str,
    ) -> BookMetadata | None:

        params = {
            "q": f"isbn:{isbn}",
            **self._key_params(),
        }

        try:
            response = requests.get(
                self.endpoint,
                params=params,
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

        items = data.get(
            "items",
            [],
        )

        if not items:
            return None

        for item in items:
            search_volume = item.get(
                "volumeInfo",
                {},
            )

            identifiers = search_volume.get(
                "industryIdentifiers",
                [],
            )

            returned_isbns = {
                str(
                    identifier.get(
                        "identifier",
                        "",
                    )
                ).replace("-", "")
                for identifier in identifiers
            }

            if isbn not in returned_isbns:
                continue

            full_item = self._get_full_volume(
                item.get(
                    "id",
                    "",
                )
            )

            if full_item:
                volume = full_item.get(
                    "volumeInfo",
                    {},
                )
            else:
                volume = search_volume

            image_links = volume.get(
                "imageLinks",
                {},
            )

            series_id, series_number = (
                self._series_details(
                    volume
                )
            )

            series_title = self._get_series_title(
                series_id
            )

            return BookMetadata(
                isbn=isbn,
                title=volume.get(
                    "title",
                    "",
                ),
                subtitle=volume.get(
                    "subtitle",
                    "",
                ),
                authors=volume.get(
                    "authors",
                    [],
                ),
                publisher=volume.get(
                    "publisher",
                    "",
                ),
                published_date=volume.get(
                    "publishedDate",
                    "",
                ),
                format="",
                series=series_title,
                series_number=series_number,
                description=volume.get(
                    "description",
                    "",
                ),
                thumbnail_url=(
                    image_links.get(
                        "thumbnail",
                        "",
                    )
                    or image_links.get(
                        "smallThumbnail",
                        "",
                    )
                ),
                source=self.name,
            )

        return None
