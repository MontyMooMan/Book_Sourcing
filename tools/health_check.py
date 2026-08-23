from core.health import (
    ConnectorHealthService,
    HealthCase,
)

from suppliers.bookxcess import BookXcessSupplier
from suppliers.bookdelivery import BookDeliverySupplier
from suppliers.mph import MPHSupplier


checks = [
    (
        BookXcessSupplier(),
        HealthCase(
            isbn="9780603570209",
        ),
    ),
    (
        BookDeliverySupplier(),
        HealthCase(
            isbn="9781837251544",
            expected_offer_types=[
                "Cheaper",
                "Faster",
            ],
        ),
    ),
    (
        MPHSupplier(),
        HealthCase(
            isbn="9781837251544",
        ),
    ),
]


service = ConnectorHealthService()


for supplier, case in checks:

    result = service.check(
        supplier,
        case,
    )

    print()
    print("=" * 60)
    print(result.supplier)
    print("=" * 60)

    print(
        f"Status: {result.status.upper()}"
    )

    print(
        f"Control ISBN: {result.isbn}"
    )

    print(
        f"Offers returned: "
        f"{result.offer_count}"
    )

    if not result.issues:
        print(
            "All expected data returned."
        )

    else:
        print("Issues:")

        for issue in result.issues:
            print(
                f"  - {issue.field}: "
                f"{issue.message}"
            )