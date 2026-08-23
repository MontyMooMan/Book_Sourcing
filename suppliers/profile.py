from dataclasses import dataclass, field
from enum import Enum


class SupplierScope(str, Enum):
    LOCAL = "local"
    NATIONAL = "national"
    REGIONAL = "regional"
    INTERNATIONAL = "international"


class ConnectorType(str, Enum):
    OFFICIAL_API = "official_api"
    INTERNAL_API = "internal_api"
    WEBSITE = "website"
    INSTITUTIONAL = "institutional"
    UNKNOWN = "unknown"


@dataclass
class AffiliateProfile:
    available: bool = False
    network: str = ""
    commission: str = ""
    cookie_days: int | None = None


@dataclass
class SupplierProfile:
    display_name: str

    # Where the supplier/company originates.
    home_country: str | None = None

    # The storefront/market represented by THIS connector.
    # Example: Kinokuniya Malaysia -> "MY"
    market: str | None = None

    # Countries where the supplier has a genuine local
    # storefront or operating presence.
    operating_markets: tuple[str, ...] = field(
        default_factory=tuple
    )

    scope: SupplierScope = SupplierScope.NATIONAL

    independent: bool = False
    marketplace: bool = False
    institutional: bool = False

    # Countries the relevant storefront will ship to.
    # This is separate from operating_markets.
    shipping_countries: tuple[str, ...] = field(
        default_factory=tuple
    )

    # Useful where a retailer states broad regional coverage
    # but we do not yet have an exact country list.
    shipping_regions: tuple[str, ...] = field(
        default_factory=tuple
    )

    # Only True where we are confident shipping is genuinely global.
    global_shipping: bool = False

    connector_type: ConnectorType = (
        ConnectorType.UNKNOWN
    )

    affiliate: AffiliateProfile = field(
        default_factory=AffiliateProfile
    )

    def operates_in(
        self,
        country_code: str,
    ) -> bool:
        return (
            country_code
            in self.operating_markets
        )

    def ships_to(
        self,
        country_code: str,
    ) -> bool:
        if self.global_shipping:
            return True

        return (
            country_code
            in self.shipping_countries
        )

    def relevant_to(
        self,
        country_code: str,
    ) -> bool:
        return (
            self.operates_in(country_code)
            or self.ships_to(country_code)
        )