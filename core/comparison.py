from decimal import Decimal

from core.models import Offer


def comparison_price_myr(
    offer: Offer,
) -> Decimal | None:
    """
    Return the per-copy MYR value that is safe to use for ranking.

    Structured landed cost wins whenever it is available.

    Offers with conditional or unknown shipping are not ranked because
    the final cost is not yet known.

    Suppliers that do not yet expose structured shipping data retain
    the existing behaviour: an MYR item price is treated as the
    comparison price.
    """

    if not offer.available:
        return None

    if offer.landed_price_myr is not None:
        return offer.landed_price_myr

    if offer.shipping_type in {
        "conditional",
        "unknown",
    }:
        return None

    if (
        offer.currency == "MYR"
        and offer.price is not None
        and not offer.shipping_type
    ):
        return offer.price

    return None


def cheapest_offer(
    offers: list[Offer],
    quantity: int = 1,
) -> Offer | None:

    candidates = []

    for offer in offers:
        if (
            offer.stock_quantity is not None
            and offer.stock_quantity < quantity
        ):
            continue

        landed = comparison_price_myr(
            offer
        )

        if landed is None:
            continue

        candidates.append(
            (
                landed,
                offer,
            )
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[0]
    )

    return candidates[0][1]


def fastest_offer(
    offers: list[Offer],
    quantity: int = 1,
) -> Offer | None:

    candidates = []

    for offer in offers:
        if not offer.available:
            continue

        if (
            offer.stock_quantity is not None
            and offer.stock_quantity < quantity
        ):
            continue

        if offer.delivery_min_days is None:
            continue

        candidates.append(
            offer
        )

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda offer: (
            offer.delivery_min_days,
            offer.delivery_max_days
            if offer.delivery_max_days is not None
            else offer.delivery_min_days,
        ),
    )
