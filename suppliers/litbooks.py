import json
from decimal import Decimal

import requests
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


class LitBooksSupplier(Supplier):
    name = "Lit Books"

    capabilities = SupplierCapabilities(
        price=True,
        availability=True,
        stock_quantity=False,
        delivery=False,
        publisher=False,
        format=False,
    )

    profile = SupplierProfile(
        display_name="Lit Books",
        home_country="MY",
        market="MY",
        operating_markets=("MY",),
        scope=SupplierScope.LOCAL,
        independent=True,
        marketplace=False,
        institutional=False,
        shipping_countries=("MY",),
        global_shipping=False,
        connector_type=ConnectorType.WEBSITE,
        affiliate=AffiliateProfile(
            available=False,
        ),
    )

    BASE_URL = (
        "https://shop.litbooks.com.my/products/"
    )

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/126.0 Safari/537.36"
        ),
        "Accept-Language": "en-GB,en;q=0.9",
    }

    def lookup(self, isbn: str) -> list[Offer]:
        url = f"{self.BASE_URL}{isbn}"

        try:
            response = requests.get(
                url,
                headers=self.HEADERS,
                timeout=15,
            )

        except requests.RequestException as exc:
            print(
                f"Lit Books request failed "
                f"for {isbn}: {exc}"
            )
            return []

        if response.status_code == 404:
            return []

        if response.status_code != 200:
            print(
                f"Lit Books returned HTTP "
                f"{response.status_code} "
                f"for {isbn}"
            )
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        product_data = (
            self._find_product_json(
                soup
            )
        )

        if not product_data:
            return []

        page_isbn = str(
            product_data.get(
                "gtin",
                "",
            )
        ).strip()

        if (
            page_isbn
            and page_isbn != isbn
        ):
            return []

        offers = product_data.get(
            "offers"
        )

        if isinstance(
            offers,
            list,
        ):
            if not offers:
                return []

            offer_data = offers[0]

        elif isinstance(
            offers,
            dict,
        ):
            offer_data = offers

        else:
            return []

        price = self._parse_price(
            offer_data.get(
                "price"
            )
        )

        currency = (
            offer_data.get(
                "priceCurrency"
            )
            or "MYR"
        )

        availability_value = str(
            offer_data.get(
                "availability",
                "",
            )
        )

        available = (
            availability_value
            .lower()
            .endswith(
                "/instock"
            )
        )

        product_url = (
            product_data.get(
                "url"
            )
            or offer_data.get(
                "url"
            )
            or url
        )

        title = (
            product_data.get(
                "name"
            )
            or ""
        ).strip()

        return [
            Offer(
                isbn=isbn,
                supplier=self.name,
                title=title,
                price=price,
                currency=currency,
                available=available,
                offer_type="",
                rrp=None,
                stock_quantity=None,
                delivery_min_days=None,
                delivery_max_days=None,
                delivery_text="",
                publisher="",
                format="",
                url=product_url,
            )
        ]

    def _find_product_json(
        self,
        soup: BeautifulSoup,
    ) -> dict | None:

        scripts = soup.find_all(
            "script",
            {
                "type": (
                    "application/ld+json"
                )
            },
        )

        for script in scripts:
            raw = (
                script.string
                or script.get_text()
                or ""
            ).strip()

            if not raw:
                continue

            try:
                data = json.loads(
                    raw
                )

            except json.JSONDecodeError:
                continue

            product = (
                self._extract_product(
                    data
                )
            )

            if product:
                return product

        return None

    def _extract_product(
        self,
        data,
    ) -> dict | None:

        if isinstance(
            data,
            dict,
        ):
            if (
                data.get("@type")
                == "Product"
            ):
                return data

            graph = data.get(
                "@graph"
            )

            if isinstance(
                graph,
                list,
            ):
                for item in graph:
                    product = (
                        self._extract_product(
                            item
                        )
                    )

                    if product:
                        return product

        elif isinstance(
            data,
            list,
        ):
            for item in data:
                product = (
                    self._extract_product(
                        item
                    )
                )

                if product:
                    return product

        return None

    def _parse_price(
        self,
        value,
    ) -> Decimal | None:

        if value is None:
            return None

        try:
            return Decimal(
                str(value)
                .replace(",", "")
                .strip()
            )

        except Exception:
            return None
