import re
import requests

from decimal import Decimal
from typing import Optional

from core.health import SupplierCapabilities
from core.models import Offer
from suppliers.base import Supplier

from suppliers.profile import (
    AffiliateProfile,
    ConnectorType,
    SupplierProfile,
    SupplierScope,
)

class BookXcessSupplier(Supplier):
    profile = SupplierProfile(
        display_name="BookXcess",
        home_country="MY",
        market="MY",
        operating_markets=("MY",),
        scope=SupplierScope.NATIONAL,
        independent=False,
        marketplace=False,
        institutional=False,
        shipping_countries=("MY",),
        shipping_regions=(),
        global_shipping=False,
        connector_type=ConnectorType.INTERNAL_API,
        affiliate=AffiliateProfile(
            available=False,
        ),
    )
    name = "BookXcess"

    capabilities = SupplierCapabilities(
        title=True,
        price=True,
        availability=True,
        url=True,
        publisher=True,
        format=False,
        delivery=False,
        stock_quantity=False,
        multiple_offers=False,
    )

    endpoint = "https://www.bookxcess.com/api/2026-04/graphql.json"
    token = "3717c3c1eba3fc069cc4a113960d48db"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120 Safari/537.36"
        )
    }

    def lookup(
        self,
        isbn: str,
    ) -> list[Offer]:
        isbn = self._clean_isbn(isbn)

        if not isbn:
            return []

        query = """
        query SearchProduct($query: String!) {
          search(
            query: $query
            first: 10
            types: [PRODUCT]
          ) {
            nodes {
              ... on Product {
                id
                title
                handle
                productType
                vendor
                availableForSale

                variants(first: 20) {
                  nodes {
                    barcode
                    sku
                    availableForSale

                    price {
                      amount
                      currencyCode
                    }

                    compareAtPrice {
                      amount
                      currencyCode
                    }
                  }
                }
              }
            }
          }
        }
        """

        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Storefront-Access-Token": self.token,
        }

        payload = {
            "query": query,
            "variables": {
                "query": isbn,
            },
        }

        try:
            response = requests.post(
                self.endpoint,
                headers=headers,
                json=payload,
                timeout=15,
            )

            response.raise_for_status()

        except requests.RequestException as exc:
            print(
                f"{self.name} request failed: {exc}"
            )
            return []

        try:
            data = response.json()

        except ValueError:
            print(
                f"{self.name}: invalid JSON response"
            )
            return []

        if "errors" in data:
            print(
                f"{self.name} GraphQL error:"
            )
            print(
                data["errors"]
            )
            return []

        nodes = (
            data
            .get("data", {})
            .get("search", {})
            .get("nodes", [])
        )

        for product in nodes:
            variants = (
                product
                .get("variants", {})
                .get("nodes", [])
            )

            for variant in variants:
                barcode = self._clean_isbn(
                    variant.get(
                        "barcode",
                        "",
                    )
                )

                sku = self._clean_isbn(
                    variant.get(
                        "sku",
                        "",
                    )
                )

                if isbn not in (
                    barcode,
                    sku,
                ):
                    continue

                price_data = (
                    variant.get("price")
                    or {}
                )

                rrp_data = (
                    variant.get(
                        "compareAtPrice"
                    )
                    or {}
                )

                handle = product.get(
                    "handle",
                    "",
                )

                product_url = ""

                if handle:
                    product_url = (
                        "https://www.bookxcess.com/products/"
                        + handle
                    )

                stock_quantity = None

                if product_url:
                    stock_quantity = (
                        self._get_stock_quantity(
                            product_url
                        )
                    )

                offer = Offer(
                    isbn=isbn,
                    supplier=self.name,
                    title=product.get(
                        "title",
                        "",
                    ),
                    price=self._to_decimal(
                        price_data.get(
                            "amount"
                        )
                    ),
                    currency=(
                        price_data.get(
                            "currencyCode"
                        )
                        or "MYR"
                    ),
                    available=bool(
                        variant.get(
                            "availableForSale"
                        )
                    ),
                    rrp=self._to_decimal(
                        rrp_data.get(
                            "amount"
                        )
                    ),
                    stock_quantity=stock_quantity,
                    publisher=product.get(
                        "vendor",
                        "",
                    ),
                    format="",
                    url=product_url,
                )

                return [
                    offer
                ]

        return []

    def _get_stock_quantity(
        self,
        product_url: str,
    ) -> Optional[int]:
        try:
            response = requests.get(
                product_url,
                headers=self.headers,
                timeout=15,
            )

            response.raise_for_status()

        except requests.RequestException as exc:
            print(
                f"{self.name} stock lookup failed: {exc}"
            )
            return None

        text = response.text

        patterns = [
            r"Only\s+(\d+)\s+units?\s+left",
            r"(\d+)\s+units?\s+available",
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            )

            if match:
                try:
                    return int(
                        match.group(1)
                    )
                except ValueError:
                    return None

        if re.search(
            r"\bSold Out\b",
            text,
            flags=re.IGNORECASE,
        ):
            return 0

        return None

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

    @staticmethod
    def _to_decimal(
        value,
    ) -> Optional[Decimal]:
        if value in (
            None,
            "",
        ):
            return None

        try:
            return Decimal(
                str(value)
            )

        except Exception:
            return None