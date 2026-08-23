from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core.models import Offer


@dataclass
class SupplierCapabilities:
    title: bool = True
    price: bool = True
    availability: bool = True
    url: bool = True

    publisher: bool = False
    format: bool = False
    delivery: bool = False
    stock_quantity: bool = False
    multiple_offers: bool = False


@dataclass
class HealthCase:
    isbn: str

    expected_offer_types: list[str] = field(
        default_factory=list
    )


@dataclass
class HealthIssue:
    field: str
    message: str


@dataclass
class HealthResult:
    supplier: str
    isbn: str
    status: str

    checked_at: datetime

    offer_count: int

    issues: list[HealthIssue] = field(
        default_factory=list
    )


class ConnectorHealthService:

    def check(
        self,
        supplier,
        case: HealthCase,
    ) -> HealthResult:

        checked_at = datetime.now()

        try:
            offers = supplier.lookup(
                case.isbn
            )

        except Exception as exc:
            return HealthResult(
                supplier=supplier.name,
                isbn=case.isbn,
                status="broken",
                checked_at=checked_at,
                offer_count=0,
                issues=[
                    HealthIssue(
                        field="connector",
                        message=(
                            f"Connector raised an exception: "
                            f"{exc}"
                        ),
                    )
                ],
            )

        # IMPORTANT:
        # A normal user ISBN being absent is not a health problem.
        #
        # These ISBNs, however, are deliberately selected
        # health-check controls that should return data.
        #
        # Therefore no offer here is a warning rather than
        # automatically calling the connector broken.
        if not offers:
            return HealthResult(
                supplier=supplier.name,
                isbn=case.isbn,
                status="warning",
                checked_at=checked_at,
                offer_count=0,
                issues=[
                    HealthIssue(
                        field="control_isbn",
                        message=(
                            "Control ISBN returned no offers."
                        ),
                    )
                ],
            )

        issues = []

        capabilities = supplier.capabilities

        for index, offer in enumerate(
            offers,
            start=1,
        ):
            prefix = f"Offer {index}"

            self._check_offer(
                offer=offer,
                capabilities=capabilities,
                issues=issues,
                prefix=prefix,
            )

        if case.expected_offer_types:
            actual_types = {
                offer.offer_type
                for offer in offers
                if offer.offer_type
            }

            for expected_type in (
                case.expected_offer_types
            ):
                if expected_type not in actual_types:
                    issues.append(
                        HealthIssue(
                            field="offer_type",
                            message=(
                                f"Expected offer type "
                                f"'{expected_type}' "
                                f"was not returned."
                            ),
                        )
                    )

        if (
            capabilities.multiple_offers
            and len(offers) < 2
        ):
            issues.append(
                HealthIssue(
                    field="multiple_offers",
                    message=(
                        "Supplier is expected to return "
                        "multiple offers but returned "
                        f"{len(offers)}."
                    ),
                )
            )

        status = (
            "healthy"
            if not issues
            else "warning"
        )

        return HealthResult(
            supplier=supplier.name,
            isbn=case.isbn,
            status=status,
            checked_at=checked_at,
            offer_count=len(offers),
            issues=issues,
        )

    @staticmethod
    def _check_offer(
        offer: Offer,
        capabilities: SupplierCapabilities,
        issues: list[HealthIssue],
        prefix: str,
    ) -> None:

        if (
            capabilities.title
            and not offer.title.strip()
        ):
            issues.append(
                HealthIssue(
                    field="title",
                    message=f"{prefix}: title missing.",
                )
            )

        if capabilities.price:
            if (
                offer.price is None
                or offer.price <= 0
            ):
                issues.append(
                    HealthIssue(
                        field="price",
                        message=(
                            f"{prefix}: valid price missing."
                        ),
                    )
                )

        if (
            capabilities.availability
            and not isinstance(
                offer.available,
                bool,
            )
        ):
            issues.append(
                HealthIssue(
                    field="availability",
                    message=(
                        f"{prefix}: availability "
                        f"is not a boolean."
                    ),
                )
            )

        if (
            capabilities.url
            and not offer.url.startswith(
                ("http://", "https://")
            )
        ):
            issues.append(
                HealthIssue(
                    field="url",
                    message=(
                        f"{prefix}: valid product URL "
                        f"missing."
                    ),
                )
            )

        if (
            capabilities.publisher
            and not offer.publisher.strip()
        ):
            issues.append(
                HealthIssue(
                    field="publisher",
                    message=(
                        f"{prefix}: publisher missing."
                    ),
                )
            )

        if (
            capabilities.format
            and not offer.format.strip()
        ):
            issues.append(
                HealthIssue(
                    field="format",
                    message=(
                        f"{prefix}: format missing."
                    ),
                )
            )

        if capabilities.delivery:
            if (
                offer.delivery_min_days is None
                or offer.delivery_max_days is None
                or not offer.delivery_text
            ):
                issues.append(
                    HealthIssue(
                        field="delivery",
                        message=(
                            f"{prefix}: delivery "
                            f"information missing."
                        ),
                    )
                )

        if capabilities.stock_quantity:
            if offer.stock_quantity is None:
                issues.append(
                    HealthIssue(
                        field="stock_quantity",
                        message=(
                            f"{prefix}: stock quantity "
                            f"missing."
                        ),
                    )
                )