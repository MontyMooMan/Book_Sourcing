from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class Offer:
    isbn: str
    supplier: str
    title: str
    price: Optional[Decimal]
    currency: str
    available: bool
    offer_type: str = ""
    rrp: Optional[Decimal] = None
    stock_quantity: Optional[int] = None
    delivery_min_days: Optional[int] = None
    delivery_max_days: Optional[int] = None
    delivery_text: str = ""
    publisher: str = ""
    format: str = ""
    url: str = ""

    # Structured delivery / landed-cost fields.
    shipping_cost: Optional[Decimal] = None
    shipping_currency: str = ""
    shipping_type: str = ""  # paid / free / conditional / unknown

    # MYR comparison values.  These are intentionally estimates when
    # source prices are not already in MYR.
    estimated_price_myr: Optional[Decimal] = None
    estimated_shipping_myr: Optional[Decimal] = None
    landed_price_myr: Optional[Decimal] = None
    conversion_estimated: bool = False
