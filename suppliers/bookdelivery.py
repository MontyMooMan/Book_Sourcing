import re
import requests

from decimal import Decimal
from typing import Optional

from bs4 import BeautifulSoup

from core.health import SupplierCapabilities
from core.models import Offer
from suppliers.base import Supplier

from suppliers.profile import (
    AffiliateProfile,
    ConnectorType,
    SupplierProfile,
    SupplierScope,
)

class BookDeliverySupplier(Supplier):
    name = "BookDelivery"
    profile = SupplierProfile(
        display_name="BookDelivery",
        home_country=None,
        market="MY",
        operating_markets=(),
        scope=SupplierScope.INTERNATIONAL,
        independent=False,
        marketplace=False,
        institutional=False,
        shipping_countries=("MY",),
        global_shipping=False,
        connector_type=ConnectorType.WEBSITE,
        affiliate=AffiliateProfile(
            available=False,
        ),
    )
    capabilities = SupplierCapabilities(
        title=True,
        price=True,
        availability=True,
        url=True,
        publisher=True,
        format=True,
        delivery=True,
        stock_quantity=False,
        multiple_offers=True,
    )

    base_url = "https://www.bookdelivery.com"

    search_url = (
        "https://www.bookdelivery.com/books/search/?q={isbn}"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
    }

    def lookup(
        self,
        isbn: str,
    ) -> list[Offer]:

        isbn = self._clean_isbn(isbn)

        if not isbn:
            return []

        product_url = self._find_product_url(
            isbn
        )

        if not product_url:
            return []

        try:
            response = requests.get(
                product_url,
                headers=self.headers,
                timeout=20,
            )

            response.raise_for_status()

        except requests.RequestException as exc:
            print(
                f"{self.name} product request failed: "
                f"{exc}"
            )
            return []

        html = response.text

        if isbn not in html:
            print(
                f"{self.name}: requested ISBN "
                f"not present on product page."
            )
            return []

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        title = self._extract_title(
            soup
        )

        publisher = self._extract_metadata(
            soup,
            "Publisher",
        )

        book_format = self._extract_metadata(
            soup,
            "Format",
        )

        return self._extract_offers(
            soup=soup,
            isbn=isbn,
            title=title,
            publisher=publisher,
            book_format=book_format,
            product_url=product_url,
        )

    def _extract_offers(
        self,
        soup: BeautifulSoup,
        isbn: str,
        title: str,
        publisher: str,
        book_format: str,
        product_url: str,
    ) -> list[Offer]:

        text = soup.get_text(
            " ",
            strip=True,
        )

        offers = []

        # -------------------------
        # Cheaper option
        # -------------------------

        cheaper_match = re.search(
            r"\bCheaper\b"
            r".*?"
            r"Shipping:\s*"
            r"(\d+)\s*to\s*(\d+)\s*business days\.?"
            r".*?"
            r"RM\s*"
            r"([0-9]+(?:[.,][0-9]{1,2})?)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if cheaper_match:
            delivery_min_days = int(
                cheaper_match.group(1)
            )

            delivery_max_days = int(
                cheaper_match.group(2)
            )

            price = Decimal(
                cheaper_match.group(3)
                .replace(",", ".")
            )

            offers.append(
                Offer(
                    isbn=isbn,
                    supplier=self.name,
                    title=title,
                    price=price,
                    currency="MYR",
                    available=True,
                    offer_type="Cheaper",
                    rrp=None,
                    stock_quantity=None,
                    delivery_min_days=delivery_min_days,
                    delivery_max_days=delivery_max_days,
                    delivery_text=(
                        f"{delivery_min_days} to "
                        f"{delivery_max_days} "
                        f"business days"
                    ),
                    publisher=publisher,
                    format=book_format,
                    url=product_url,
                )
            )

        # -------------------------
        # Faster option
        # -------------------------

        faster_match = re.search(
            r"\bFaster\b"
            r".*?"
            r"Shipping:\s*"
            r"(\d+)\s*to\s*(\d+)\s*business days\.?"
            r".*?"
            r"RM\s*"
            r"([0-9]+(?:[.,][0-9]{1,2})?)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if faster_match:
            delivery_min_days = int(
                faster_match.group(1)
            )

            delivery_max_days = int(
                faster_match.group(2)
            )

            price = Decimal(
                faster_match.group(3)
                .replace(",", ".")
            )

            offers.append(
                Offer(
                    isbn=isbn,
                    supplier=self.name,
                    title=title,
                    price=price,
                    currency="MYR",
                    available=True,
                    offer_type="Faster",
                    rrp=None,
                    stock_quantity=None,
                    delivery_min_days=delivery_min_days,
                    delivery_max_days=delivery_max_days,
                    delivery_text=(
                        f"{delivery_min_days} to "
                        f"{delivery_max_days} "
                        f"business days"
                    ),
                    publisher=publisher,
                    format=book_format,
                    url=product_url,
                )
            )

        # -------------------------
        # Fallback
        # -------------------------

        if not offers:
            price = self._extract_price(
                soup
            )

            if price is not None:
                offers.append(
                    Offer(
                        isbn=isbn,
                        supplier=self.name,
                        title=title,
                        price=price,
                        currency="MYR",
                        available=True,
                        offer_type="",
                        rrp=None,
                        stock_quantity=None,
                        delivery_min_days=None,
                        delivery_max_days=None,
                        delivery_text="",
                        publisher=publisher,
                        format=book_format,
                        url=product_url,
                    )
                )

        return offers

    def _find_product_url(
        self,
        isbn: str,
    ) -> Optional[str]:

        url = self.search_url.format(
            isbn=isbn
        )

        try:
            response = requests.get(
                url,
                headers=self.headers,
                timeout=20,
            )

            response.raise_for_status()

        except requests.RequestException as exc:
            print(
                f"{self.name} search failed: "
                f"{exc}"
            )
            return None

        html = response.text

        pattern = re.compile(
            rf'href=["\']'
            rf'([^"\']*/{re.escape(isbn)}/p/\d+[^"\']*)'
            rf'["\']',
            re.IGNORECASE,
        )

        match = pattern.search(
            html
        )

        if not match:
            print(
                f"{self.name}: no exact product "
                f"link found for {isbn}"
            )
            return None

        product_url = match.group(1)

        product_url = (
            product_url
            .replace("&amp;", "&")
            .replace("&#x2F;", "/")
        )

        if product_url.startswith("/"):
            product_url = (
                self.base_url
                + product_url
            )

        product_url = re.sub(
            r"bookdelivery\.com/[a-z]{2}-en/",
            "bookdelivery.com/my-en/",
            product_url,
            flags=re.IGNORECASE,
        )

        return product_url

    @staticmethod
    def _extract_title(
        soup: BeautifulSoup,
    ) -> str:

        h1 = soup.find("h1")

        if h1:
            return h1.get_text(
                " ",
                strip=True,
            )

        if soup.title:
            title = soup.title.get_text(
                " ",
                strip=True,
            )

            return re.sub(
                r"\s*-\s*BookDelivery.*$",
                "",
                title,
                flags=re.IGNORECASE,
            )

        return ""

    @staticmethod
    def _extract_metadata(
        soup: BeautifulSoup,
        field_name: str,
    ) -> str:

        target = field_name.lower()

        for element in soup.find_all(
            [
                "li",
                "div",
                "p",
                "tr",
                "dt",
            ]
        ):
            text = element.get_text(
                " ",
                strip=True,
            )

            if not text:
                continue

            if not text.lower().startswith(
                target
            ):
                continue

            value = re.sub(
                rf"^{re.escape(field_name)}"
                rf"\s*:?\s*",
                "",
                text,
                flags=re.IGNORECASE,
            ).strip()

            if (
                value
                and value.lower() != target
                and len(value) < 150
            ):
                return value

        return ""

    @staticmethod
    def _extract_price(
        soup: BeautifulSoup,
    ) -> Optional[Decimal]:

        candidates = []

        for element in soup.find_all(
            True
        ):
            classes = " ".join(
                element.get(
                    "class",
                    [],
                )
            ).lower()

            element_id = str(
                element.get(
                    "id",
                    "",
                )
            ).lower()

            if (
                "price" not in classes
                and "precio" not in classes
                and "price" not in element_id
                and "precio" not in element_id
            ):
                continue

            text = element.get_text(
                " ",
                strip=True,
            )

            for match in re.finditer(
                r"\bRM\s*"
                r"([0-9]+(?:[.,][0-9]{1,2})?)",
                text,
                flags=re.IGNORECASE,
            ):
                value = Decimal(
                    match.group(1)
                    .replace(",", ".")
                )

                if value >= Decimal("1"):
                    candidates.append(
                        value
                    )

        if not candidates:
            return None

        return min(
            candidates
        )

    @staticmethod
    def _clean_isbn(
        value: str,
    ) -> str:

        return "".join(
            char
            for char in str(value).upper()
            if char.isdigit()
            or char == "X"
        )