from core.health import SupplierCapabilities

from suppliers.amazon_base import AmazonBaseSupplier
from suppliers.profile import (
    AffiliateProfile,
    ConnectorType,
    SupplierProfile,
    SupplierScope,
)


class AmazonUSSupplier(AmazonBaseSupplier):
    name = "Amazon US"

    BASE_URL = "https://www.amazon.com"
    CURRENCY = "USD"
    LOCALE = "en-US"

    capabilities = SupplierCapabilities(
        price=True,
        availability=True,
        stock_quantity=False,
        delivery=False,
        publisher=False,
        format=True,
    )

    profile = SupplierProfile(
        display_name="Amazon US",
        home_country="US",
        market="US",
        operating_markets=("US",),
        scope=SupplierScope.NATIONAL,
        independent=False,
        marketplace=True,
        institutional=False,
        shipping_countries=(
            "US",
            "MY",
        ),
        global_shipping=False,
        connector_type=ConnectorType.WEBSITE,
        affiliate=AffiliateProfile(
            available=True,
            network="Amazon Associates US",
        ),
    )
