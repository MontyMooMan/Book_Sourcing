import requests

from decimal import Decimal
from typing import Optional

from core.models import Offer
from suppliers.base import Supplier

from core.health import SupplierCapabilities

from suppliers.profile import (
    AffiliateProfile,
    ConnectorType,
    SupplierProfile,
    SupplierScope,
)

class MPHSupplier(Supplier):
    profile = SupplierProfile(
        display_name="MPH",
        home_country="MY",
        market="MY",
        operating_markets=("MY",),
        scope=SupplierScope.NATIONAL,
        independent=False,
        marketplace=False,
        institutional=True,
        shipping_countries=("MY",),
        global_shipping=False,
        connector_type=ConnectorType.INTERNAL_API,
        affiliate=AffiliateProfile(
            available=False,
        ),
    )
    capabilities = SupplierCapabilities(
        title=True,
        price=True,
        availability=True,
        url=True,
        stock_quantity=True,
    )
    name = "MPH"

    endpoint = (
        "https://services.mybcapps.com/"
        "bc-sf-filter/search/suggest"
    )

    shop = "mph-online.myshopify.com"

    base_url = "https://mphonline.com"

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

        params = {
            "shop": self.shop,
            "q": isbn,
        }

        try:
            response = requests.get(
                self.endpoint,
                params=params,
                headers=self.headers,
                timeout=20,
            )

            response.raise_for_status()

        except requests.RequestException as exc:
            print(
                f"{self.name} search failed: {exc}"
            )
            return []

        try:
            data = response.json()

        except ValueError:
            print(
                f"{self.name}: invalid JSON response"
            )
            return []

        products = data.get(
            "products",
            [],
        )

        for product in products:
            offer = self._product_to_offer(
                product,
                isbn,
            )

            if offer:
                return [offer]

        return []

    def _product_to_offer(
        self,
        product: dict,
        isbn: str,
    ) -> Optional[Offer]:

        variants = product.get(
            "variants",
            [],
        )

        matching_variant = None

        for variant in variants:
            sku = self._clean_isbn(
                variant.get(
                    "sku",
                    "",
                )
            )

            barcode = self._clean_isbn(
                variant.get(
                    "barcode",
                    "",
                )
            )

            if isbn in (
                sku,
                barcode,
            ):
                matching_variant = variant
                break

        if not matching_variant:
            return None

        price_value = matching_variant.get(
            "price"
        )

        price = None

        if price_value is not None:
            try:
                price = Decimal(
                    str(price_value)
                )

            except Exception:
                price = None

        available = bool(
            matching_variant.get(
                "available",
                product.get(
                    "available",
                    False,
                ),
            )
        )

        title = product.get(
            "title",
            "",
        )

        handle = product.get(
            "handle",
            "",
        )

        product_url = ""

        if handle:
            product_url = (
                f"{self.base_url}/products/"
                f"{handle}"
            )

        publisher = (
            product.get(
                "vendor"
            )
            or ""
        )

        book_format = self._extract_format(
            product
        )

        rrp = self._extract_rrp(
            matching_variant
        )

        stock_quantity = matching_variant.get(
            "inventory_quantity"
        )

        return Offer(
            isbn=isbn,
            supplier=self.name,
            title=title,
            price=price,
            currency="MYR",
            available=available,
            rrp=rrp,
            stock_quantity=stock_quantity,
            publisher=publisher,
            format=book_format,
            url=product_url,
        )

    @staticmethod
    def _extract_rrp(
        variant: dict,
    ) -> Optional[Decimal]:

        value = variant.get(
            "compare_at_price"
        )

        if value in (
            None,
            "",
            "0",
            "0.00",
        ):
            return None

        try:
            rrp = Decimal(
                str(value)
            )

            if rrp <= 0:
                return None

            return rrp

        except Exception:
            return None

    @staticmethod
    def _extract_format(
        product: dict,
    ) -> str:

        for key in (
            "product_type",
            "type",
        ):
            value = product.get(
                key
            )

            if value:
                return str(
                    value
                )

        return ""

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