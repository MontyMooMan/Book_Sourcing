from core.health import SupplierCapabilities

from suppliers.amazon_base import AmazonBaseSupplier
from suppliers.profile import (
    AffiliateProfile,
    ConnectorType,
    SupplierProfile,
    SupplierScope,
)


class AmazonUKSupplier(AmazonBaseSupplier):
    name = "Amazon UK"

    BASE_URL = "https://www.amazon.co.uk"
    CURRENCY = "GBP"
    LOCALE = "en-GB"

    capabilities = SupplierCapabilities(
        price=True,
        availability=True,
        stock_quantity=False,
        delivery=False,
        publisher=False,
        format=True,
    )

    profile = SupplierProfile(
        display_name="Amazon UK",
        home_country="GB",
        market="GB",
        operating_markets=("GB",),
        scope=SupplierScope.NATIONAL,
        independent=False,
        marketplace=True,
        institutional=False,
        shipping_countries=(
            "GB",
            "MY",
        ),
        global_shipping=False,
        connector_type=ConnectorType.WEBSITE,
        affiliate=AffiliateProfile(
            available=True,
            network="Amazon Associates UK",
        ),
    )
