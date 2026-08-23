from bibliography.cache import MetadataCache
from bibliography.models import BookMetadata


class BibliographyService:

    def __init__(
        self,
        providers,
        cache: MetadataCache | None = None,
    ):
        self.providers = list(
            providers
        )

        self.cache = (
            cache
            if cache is not None
            else MetadataCache()
        )

    @staticmethod
    def _merge(
        primary: BookMetadata,
        supplement: BookMetadata,
    ) -> tuple[BookMetadata, bool]:

        changed = False

        text_fields = (
            "title",
            "subtitle",
            "publisher",
            "published_date",
            "format",
            "series",
            "series_number",
            "description",
            "thumbnail_url",
        )

        for field_name in text_fields:
            current_value = getattr(
                primary,
                field_name,
                "",
            )

            supplement_value = getattr(
                supplement,
                field_name,
                "",
            )

            if (
                not current_value
                and supplement_value
            ):
                setattr(
                    primary,
                    field_name,
                    supplement_value,
                )
                changed = True

        if (
            not primary.authors
            and supplement.authors
        ):
            primary.authors = list(
                supplement.authors
            )
            changed = True

        return primary, changed

    def lookup(
        self,
        isbn: str,
    ) -> BookMetadata | None:

        cached = self.cache.get(
            isbn
        )

        if cached:
            print(
                f"{isbn} | Metadata cache hit"
            )
            return cached

        print(
            f"{isbn} | Metadata cache miss"
        )

        combined: BookMetadata | None = None
        contributing_sources: list[str] = []

        for provider in self.providers:

            try:
                result = provider.lookup(
                    isbn
                )

            except Exception as exc:
                print(
                    f"{provider.name} metadata error: "
                    f"{exc}"
                )
                continue

            if (
                not result
                or not result.title
            ):
                continue

            if combined is None:
                combined = result

                if result.source:
                    contributing_sources.append(
                        result.source
                    )

                continue

            combined, changed = self._merge(
                combined,
                result,
            )

            if (
                changed
                and result.source
                and result.source
                not in contributing_sources
            ):
                contributing_sources.append(
                    result.source
                )

        if combined is None:
            return None

        if contributing_sources:
            combined.source = " + ".join(
                contributing_sources
            )

        self.cache.save(
            combined
        )

        print(
            f"{isbn} | Metadata saved "
            f"from {combined.source}"
        )

        return combined
