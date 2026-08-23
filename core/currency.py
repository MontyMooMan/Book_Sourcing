from decimal import Decimal, ROUND_HALF_UP


# Deliberately simple comparison rates.
#
# These are not intended to be checkout-accurate FX quotes.  They are
# only used to make supplier prices comparable in the sourcing tool.
# Change these values whenever you want to refresh the estimate.
FX_TO_MYR = {
    "MYR": Decimal("1.00"),
    "USD": Decimal("4.25"),
    "GBP": Decimal("5.70"),
    "SGD": Decimal("3.30"),
    "AUD": Decimal("2.80"),
}


def to_myr(
    amount: Decimal | None,
    currency: str,
) -> Decimal | None:
    if amount is None:
        return None

    rate = FX_TO_MYR.get(
        (currency or "").upper()
    )

    if rate is None:
        return None

    return (
        amount * rate
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
