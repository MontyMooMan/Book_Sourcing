import queue

import re

import subprocess

import threading

import time

from concurrent.futures import Future

from decimal import Decimal

from playwright.sync_api import (

    TimeoutError as PlaywrightTimeoutError,

    sync_playwright,

)

from core.models import Offer
from core.currency import to_myr

from suppliers.base import Supplier

















class AmazonBaseSupplier(Supplier):

    BASE_URL = ""

    CURRENCY = ""

    LOCALE = "en-GB"

    def __init__(self):

        self._browser_queue = queue.Queue()

        self._browser_thread = None

        self._browser_thread_lock = threading.Lock()

        self._shutdown_requested = False

        # Marketplace's normal currency.

        self.display_currency = self.CURRENCY

        self._active_currency = self.CURRENCY

        self.target_market = None

















    # -----------------------------------------------------

    # Configure for selected market

    # -----------------------------------------------------

    def configure_for_market(

        self,

        market: str,

        currency: str,

    ):

        self.target_market = market

        self.display_currency = (

            currency or self.CURRENCY

        )

















    # -----------------------------------------------------

    # Public lookup

    # -----------------------------------------------------

    def lookup(
        self,
        isbn: str,
    ) -> list[Offer]:

        try:
            result = self._request_lookup(
                isbn
            )

        except Exception as exc:
            print(
                f"{self.name} browser lookup "
                f"failed for {isbn}: {exc}"
            )
            return []

        if not result:
            return []

        if result.get("blocked"):
            print(
                f"{self.name} verification/block page "
                f"encountered for {isbn}"
            )
            return []

        if result.get("used_offer_only"):
            print(
                f"{self.name} used offer only for {isbn}"
            )
            return []

        condition = result.get(
            "condition",
            "",
        )

        if (
            condition
            and condition.lower() != "new"
        ):
            print(
                f"{self.name} excluded non-new offer "
                f"for {isbn}: {condition}"
            )
            return []

        price = result.get(
            "price"
        )

        if price is None:
            return []

        currency = result.get(
            "currency",
            self._active_currency,
        )

        seller = result.get(
            "seller",
            "",
        )

        delivery_text = result.get(
            "delivery_text",
            "",
        )

        shipping = self._shipping_details(
            delivery_text
        )

        estimated_price_myr = to_myr(
            price,
            currency,
        )

        estimated_shipping_myr = None

        if shipping["type"] == "free":
            estimated_shipping_myr = Decimal(
                "0.00"
            )

        elif (
            shipping["type"] == "paid"
            and shipping["cost"] is not None
        ):
            estimated_shipping_myr = to_myr(
                shipping["cost"],
                shipping["currency"],
            )

        landed_price_myr = None

        if (
            estimated_price_myr is not None
            and estimated_shipping_myr is not None
        ):
            landed_price_myr = (
                estimated_price_myr
                + estimated_shipping_myr
            )

        offer_bits = [
            value
            for value in (
                condition,
                seller,
            )
            if value
        ]

        conversion_estimated = (
            currency != "MYR"
            or (
                shipping["currency"]
                and shipping["currency"] != "MYR"
            )
        )

        return [
            Offer(
                isbn=isbn,
                supplier=self.name,
                title=result.get(
                    "title",
                    "",
                ),
                price=price,
                currency=currency,
                available=result.get(
                    "available",
                    False,
                ),
                offer_type=" · ".join(
                    offer_bits
                ),
                rrp=None,
                stock_quantity=None,
                delivery_min_days=None,
                delivery_max_days=None,
                delivery_text=delivery_text,
                publisher="",
                format=result.get(
                    "format",
                    "",
                ),
                url=result.get(
                    "url",
                    "",
                ),
                shipping_cost=shipping[
                    "cost"
                ],
                shipping_currency=shipping[
                    "currency"
                ],
                shipping_type=shipping[
                    "type"
                ],
                estimated_price_myr=(
                    estimated_price_myr
                ),
                estimated_shipping_myr=(
                    estimated_shipping_myr
                ),
                landed_price_myr=(
                    landed_price_myr
                ),
                conversion_estimated=(
                    conversion_estimated
                ),
            )
        ]


    def _shipping_details(
        self,
        delivery_text: str,
    ) -> dict:

        text = self._normalise_price_text(
            delivery_text or ""
        )

        if not text:
            return {
                "type": "unknown",
                "cost": None,
                "currency": "",
            }

        lower = text.lower()

        if (
            "cannot be shipped" in lower
            or "can't be shipped" in lower
            or "cannot be delivered" in lower
            or "does not ship" in lower
        ):
            return {
                "type": "unknown",
                "cost": None,
                "currency": "",
            }

        conditional_markers = (
            "conditional free delivery",
            "eligible orders over",
            "orders over",
            "qualifying orders",
            "minimum order",
            "if you spend",
            "when you spend",
            "spend at least",
        )

        if (
            "free delivery" in lower
            and any(
                marker in lower
                for marker in conditional_markers
            )
        ):
            return {
                "type": "conditional",
                "cost": None,
                "currency": "",
            }

        # Explicit delivery charge.
        paid_match = re.search(
            r"(MYR|RM|GBP|USD|SGD|AUD|£|US\$|S\$|A\$|\$)"
            r"\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)"
            r"\s+delivery\b",
            text,
            flags=re.IGNORECASE,
        )

        if paid_match:
            token = paid_match.group(1)
            amount_text = (
                paid_match.group(2)
                .replace(",", "")
            )

            try:
                amount = Decimal(
                    amount_text
                )
            except Exception:
                amount = None

            currency = self._currency_from_token(
                token
            )

            return {
                "type": "paid",
                "cost": amount,
                "currency": currency,
            }

        if "free delivery" in lower:
            return {
                "type": "free",
                "cost": Decimal("0.00"),
                "currency": "MYR",
            }

        return {
            "type": "unknown",
            "cost": None,
            "currency": "",
        }


    @staticmethod
    def _currency_from_token(
        token: str,
    ) -> str:

        value = (
            token
            .upper()
            .strip()
        )

        if value in {
            "MYR",
            "RM",
        }:
            return "MYR"

        if value in {
            "GBP",
            "£",
        }:
            return "GBP"

        if value in {
            "USD",
            "US$",
            "$",
        }:
            return "USD"

        if value in {
            "SGD",
            "S$",
        }:
            return "SGD"

        if value in {
            "AUD",
            "A$",
        }:
            return "AUD"

        return ""


    # Browser request interface

    # -----------------------------------------------------

    def _request_lookup(

        self,

        isbn: str,

    ) -> dict:

        self._ensure_browser_worker()

        future = Future()

        self._browser_queue.put(

            (

                "lookup",

                isbn,

                future,

            )

        )

        return future.result()

















    def _ensure_browser_worker(

        self,

    ):

        with self._browser_thread_lock:

            if (

                self._browser_thread is not None

                and self._browser_thread.is_alive()

            ):

                return

            self._shutdown_requested = False

            self._browser_thread = (

                threading.Thread(

                    target=self._browser_worker,

                    name=f"{self.name}Browser",

                    daemon=True,

                )

            )

            self._browser_thread.start()

















    # -----------------------------------------------------

    # Browser worker

    # -----------------------------------------------------

    def _browser_worker(

        self,

    ):

        print(

            f"{self.name} browser worker starting..."

        )

        playwright = None

        browser = None

        context = None

        page = None

        try:

            playwright = (

                sync_playwright()

                .start()

            )

            browser = (

                playwright

                .chromium

                .launch(

                    headless=False,

                    args=[

                        "--window-size=320,240",





                    ],

                )

            )

            context = (

                browser.new_context(

                    locale=self.LOCALE,

                    viewport={

                        "width": 320,

                        "height": 240,

                    },

                )

            )

            page = context.new_page()









            # ---------------------------------------------

            # Set Amazon's display currency once

            # for this entire batch.

            # ---------------------------------------------

            self._set_display_currency(

                page

            )

            # Now that Amazon has actually navigated and

            # created a visible window, minimise it.

            self._minimise_browser_repeatedly()

            print(

                f"{self.name} browser ready "

                f"({self._active_currency})."

            )

            while not self._shutdown_requested:

                try:

                    job = (

                        self._browser_queue.get(

                            timeout=1

                        )

                    )

                except queue.Empty:

                    continue

                if not job:

                    continue

                action = job[0]

                if action == "shutdown":

                    self._browser_queue.task_done()

                    break

                if action != "lookup":

                    self._browser_queue.task_done()

                    continue

                _, isbn, future = job

                try:

                    result = (

                        self._lookup_in_browser(

                            page,

                            isbn,

                        )

                    )

                    future.set_result(

                        result

                    )

                except Exception as exc:

                    future.set_exception(

                        exc

                    )

                finally:

                    self._browser_queue.task_done()

        except Exception as exc:

            print(

                f"{self.name} browser worker "

                f"failed: {exc}"

            )

            while True:

                try:

                    job = (

                        self._browser_queue

                        .get_nowait()

                    )

                except queue.Empty:

                    break

                if (

                    job

                    and job[0] == "lookup"

                ):

                    future = job[2]

                    if not future.done():

                        future.set_exception(

                            exc

                        )

                self._browser_queue.task_done()

        finally:

            if page is not None:

                try:

                    page.close()

                except Exception:

                    pass

            if context is not None:

                try:

                    context.close()

                except Exception:

                    pass

            if browser is not None:

                try:

                    browser.close()

                except Exception:

                    pass

            if playwright is not None:

                try:

                    playwright.stop()

                except Exception:

                    pass

            print(

                f"{self.name} browser worker stopped."

            )

















    # -----------------------------------------------------

    # Amazon currency preference

    # -----------------------------------------------------

    def _set_display_currency(

        self,

        page,

    ):

        target = self.display_currency

        # No change required.

        if target == self.CURRENCY:

            self._active_currency = (

                self.CURRENCY

            )

            print(

                f"{self.name} currency: "

                f"{self._active_currency}"

            )

            return

        preference_url = (

            f"{self.BASE_URL}"

            "/customer-preferences/edit"

            "?ie=UTF8"

            "&preferencesReturnUrl=%2F"

        )

        try:

            response = page.goto(

                preference_url,

                wait_until="domcontentloaded",

                timeout=30000,

            )

            if response is not None:

                print(

                    f"{self.name} currency page HTTP:",

                    response.status,

                )

            self._settle_page(

                page

            )

            if self._is_blocked(

                page

            ):

                print(

                    f"{self.name}: Amazon blocked "

                    "currency preference page."

                )

                self._active_currency = (

                    self.CURRENCY

                )

                return

            currency_select = (

                page.locator(

                    'select[name="currencyOfPreference"]'

                )

                .first

            )

            if currency_select.count() == 0:

                print(

                    f"{self.name}: currency selector "

                    "not found."

                )

                self._active_currency = (

                    self.CURRENCY

                )

                return

            # See whether requested currency is

            # actually available on this Amazon site.

            option_values = (

                currency_select

                .locator("option")

                .evaluate_all(

                    """

                    els => els.map(

                        e => e.value

                    )

                    """

                )

            )

            if target not in option_values:

                print(

                    f"{self.name}: {target} is not "

                    "available as a display currency."

                )

                self._active_currency = (

                    self.CURRENCY

                )

                return

            currency_select.select_option(

                value=target

            )

            # Amazon preference pages normally

            # contain a submit/save button.

            submit_selectors = [

                'input[type="submit"]',

                'button[type="submit"]',

                ".a-button-input",

            ]

            submitted = False

            for selector in submit_selectors:

                button = (

                    page.locator(

                        selector

                    )

                    .first

                )

                if button.count():

                    try:

                        button.click(

                            timeout=3000

                        )

                        submitted = True

                        break

                    except Exception:

                        continue

            if submitted:

                self._settle_page(

                    page

                )

            # Read preference again if possible.

            try:

                selected_value = (

                    currency_select

                    .input_value()

                )

            except Exception:

                selected_value = target

            if selected_value == target:

                self._active_currency = (

                    target

                )

                print(

                    f"{self.name} display currency "

                    f"set to {target}."

                )

            else:

                self._active_currency = (

                    self.CURRENCY

                )

                print(

                    f"{self.name}: currency change "

                    "did not stick."

                )

        except Exception as exc:

            self._active_currency = (

                self.CURRENCY

            )

            print(

                f"{self.name} currency setup "

                f"failed: {exc}"

            )

















    # -----------------------------------------------------

    # Amazon lookup

    # -----------------------------------------------------

    def _lookup_in_browser(

        self,

        page,

        isbn: str,

    ) -> dict:

        isbn10 = self._isbn13_to_isbn10(isbn)

        if not isbn10:

            print(

                f"{self.name}: cannot convert "

                f"{isbn} to ISBN-10"

            )

            return {}

        product_url = f"{self.BASE_URL}/dp/{isbn10}"

        response = page.goto(

            product_url,

            wait_until="domcontentloaded",

            timeout=30000,

        )

        if response is not None:

            print(

                f"{self.name} product HTTP:",

                response.status,

                product_url,

            )

        self._settle_page(page)

        if self._is_blocked(page):

            return {"blocked": True}

        try:

            body_text = page.locator("body").inner_text(

                timeout=10000

            )

        except Exception:

            return {}

        lower = body_text.lower()

        missing_phrases = [

            "sorry we couldn't find that page",

            "page not found",

            "looking for something",

        ]

        if any(p in lower for p in missing_phrases):

            return {}

        page_isbn = self._extract_isbn13(body_text)

        if page_isbn and page_isbn != isbn:

            print(

                f"{self.name} ISBN mismatch: "

                f"requested {isbn}, "

                f"page returned {page_isbn}"

            )

            return {}

        title = self._text_from_selectors(

            page,

            ["#productTitle", "h1 span", "h1"],

        )

        primary = self._extract_primary_offer(page)

        condition = primary.get("condition", "")

        # Amazon UK sometimes returns HTTP 200 before the buy-box
        # price has finished rendering. Give the selected New offer
        # one short retry before treating the page as price-less.
        if (
            self.name == "Amazon UK"
            and primary.get("price") is None
            and condition.lower() == "new"
        ):
            print(
                f"{self.name}: primary price missing; "
                "waiting briefly and retrying."
            )

            try:
                page.wait_for_timeout(1800)
            except Exception:
                pass

            retry_primary = self._extract_primary_offer(
                page
            )

            if retry_primary.get("price") is not None:
                print(
                    f"{self.name}: primary price appeared "
                    "after retry."
                )

                primary = retry_primary
                condition = primary.get(
                    "condition",
                    "",
                )

        # If Amazon UK still has no price for the selected New offer,
        # inspect All Buying Options for another New copy rather than
        # immediately returning Not found.
        if (
            self.name == "Amazon UK"
            and primary.get("price") is None
            and condition.lower() == "new"
        ):
            print(
                f"{self.name}: no primary price; "
                "searching New alternative offers."
            )

            alternate = self._find_new_offer(
                page,
                isbn10,
            )

            if alternate:
                primary = alternate
                condition = primary.get(
                    "condition",
                    "",
                )

        if condition and condition.lower() != "new":

            print(

                f"{self.name} primary offer is "

                f"{condition}; searching other offers."

            )

            alternate = self._find_new_offer(

                page,

                isbn10,

            )

            if alternate:

                primary = alternate

            else:

                primary["used_offer_only"] = True

        price = primary.get("price")

        delivery_text = primary.get("delivery_text", "")

        availability_text = primary.get("availability_text", "")

        available = self._parse_availability(

            availability_text,

            price,

            delivery_text,

        )

        format_name = self._extract_format(body_text)

        print(

            f"{self.name} parsed:",

            {

                "isbn": isbn,

                "isbn10": isbn10,

                "price_text": primary.get("price_text", ""),

                "price_selector": primary.get("price_selector", ""),

                "price": price,

                "currency": primary.get(

                    "currency",

                    self._active_currency,

                ),

                "condition": primary.get("condition", ""),

                "seller": primary.get("seller", ""),

                "available": available,

                "delivery_selector": primary.get(

                    "delivery_selector",

                    "",

                ),

                "delivery": delivery_text[:140],

                "offer_source": primary.get(

                    "offer_source",

                    "primary",

                ),

                "used_offer_only": primary.get(

                    "used_offer_only",

                    False,

                ),

            },

        )

        return {

            "blocked": False,

            "title": title,

            "price": price,

            "currency": primary.get(

                "currency",

                self._active_currency,

            ),

            "condition": primary.get("condition", ""),

            "seller": primary.get("seller", ""),

            "available": available,

            "delivery_text": delivery_text,

            "format": format_name,

            "url": page.url,

            "used_offer_only": primary.get(

                "used_offer_only",

                False,

            ),

        }



    def _extract_primary_offer(
        self,
        page,
    ) -> dict:

        price_text = ""
        price_selector = ""

        # Search only Amazon's main purchasing area.  Each candidate
        # is passed through _price_from_locator(), which reconstructs
        # split Amazon prices such as:
        #
        #   MYR48 . 48
        #
        # instead of accidentally returning only "48.".
        price_containers = [
            "#corePrice_feature_div .a-price",
            "#corePriceDisplay_desktop_feature_div .a-price",
            "#apex_desktop .priceToPay",
            "#desktop_buybox .a-price",
            "#buybox .a-price",
            "#rightCol .a-price",
            ".priceToPay",
            ".apexPriceToPay",
        ]

        for selector in price_containers:
            try:
                locator = page.locator(
                    selector
                ).first

                if not locator.count():
                    continue

                candidate = self._price_from_locator(
                    locator
                )

                if candidate:
                    price_text = candidate
                    price_selector = selector
                    break

            except Exception:
                continue

        # Older / alternate Amazon layouts sometimes expose the
        # complete price in a single element rather than .a-price.
        if not price_text:
            price_text, price_selector = (
                self._text_and_selector(
                    page,
                    [
                        "#price_inside_buybox",
                        "#newBuyBoxPrice",
                        "#priceblock_ourprice",
                        "#priceblock_dealprice",
                        "#priceblock_saleprice",
                        "#price",
                    ],
                )
            )

        availability_text = self._text_from_selectors(
            page,
            [
                "#availability",
                "#outOfStock",
            ],
        )

        delivery_text, delivery_selector = (
            self._extract_primary_delivery(
                page
            )
        )

        return {
            "price_text": price_text,
            "price_selector": price_selector,
            "price": self._parse_price(
                price_text
            ),
            "currency": self._detect_currency(
                price_text
            ),
            "condition": (
                self._extract_primary_condition(
                    page
                )
            ),
            "seller": (
                self._extract_primary_seller(
                    page
                )
            ),
            "availability_text": availability_text,
            "delivery_text": delivery_text,
            "delivery_selector": delivery_selector,
            "offer_source": "primary",
        }


    def _find_new_offer(
        self,
        page,
        isbn10: str,
    ) -> dict:

        opened = False

        trigger_selectors = [
            "#buybox-see-all-buying-choices input",
            "#buybox-see-all-buying-choices a",
            "#aod-ingress-link",
            "#aod-ingress-link a",
            "a[href*='offer-listing']",
        ]

        for selector in trigger_selectors:
            try:
                trigger = page.locator(
                    selector
                ).first

                if not trigger.count():
                    continue

                trigger.click(
                    timeout=4000
                )

                try:
                    page.locator(
                        "#aod-offer, .aod-offer, "
                        "[id^='aod-offer']"
                    ).first.wait_for(
                        state="attached",
                        timeout=6000,
                    )
                except Exception:
                    pass

                opened = True

                print(
                    f"{self.name}: opened buying options "
                    f"using {selector}."
                )
                break

            except Exception:
                continue

        if not opened:
            offer_url = (
                f"{self.BASE_URL}/gp/offer-listing/"
                f"{isbn10}"
            )

            try:
                response = page.goto(
                    offer_url,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

                if response is not None:
                    print(
                        f"{self.name} offer-listing HTTP:",
                        response.status,
                    )

                self._settle_page(
                    page
                )

            except Exception as exc:
                print(
                    f"{self.name} offer-listing open failed: "
                    f"{exc}"
                )
                return {}

        if self._is_blocked(
            page
        ):
            return {}

        offers = None

        for selector in (
            "#aod-offer",
            ".aod-offer",
            "[id^='aod-offer']",
            ".olpOffer",
        ):
            try:
                candidate = page.locator(
                    selector
                )

                if candidate.count():
                    offers = candidate

                    print(
                        f"{self.name}: found "
                        f"{candidate.count()} offer blocks "
                        f"using {selector}."
                    )
                    break

            except Exception:
                continue

        if offers is None:
            print(
                f"{self.name}: no alternative "
                "offer blocks found."
            )
            return {}

        best = None

        for index in range(
            min(
                offers.count(),
                30,
            )
        ):
            offer = offers.nth(
                index
            )

            try:
                offer_text = (
                    offer.inner_text(
                        timeout=2500
                    )
                    .strip()
                )

            except Exception:
                continue

            if not offer_text:
                continue

            condition = self._condition_from_text(
                offer_text
            )

            # Reject only explicitly non-new offers.
            if (
                condition
                and condition.lower() != "new"
            ):
                continue

            price_text = self._price_from_offer_locator(
                offer
            )

            price = self._parse_price(
                price_text
            )

            if price is None:
                continue

            seller = self._seller_from_offer_locator(
                offer
            )

            delivery_text = self._delivery_from_offer_text(
                offer_text
            )

            candidate = {
                "price_text": price_text,
                "price_selector": (
                    "alternative offer block"
                ),
                "price": price,
                "currency": self._detect_currency(
                    price_text
                ),
                "condition": "New",
                "seller": seller,
                "availability_text": "In stock",
                "delivery_text": delivery_text,
                "delivery_selector": (
                    "alternative offer text"
                ),
                "offer_source": "alternative",
            }

            if (
                best is None
                or price < best["price"]
            ):
                best = candidate

        if best:
            print(
                f"{self.name}: New alternative "
                f"offer found at {best['price_text']} "
                f"from "
                f"{best['seller'] or 'unknown seller'}."
            )
        else:
            print(
                f"{self.name}: no New alternative "
                "offer found."
            )

        return best or {}


    @staticmethod
    def _normalise_price_text(
        value: str,
    ) -> str:

        if not value:
            return ""

        value = value.replace(
            "\xa0",
            " ",
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        ).strip()

        # Amazon sometimes renders the integer and decimal parts
        # separately, producing text such as "MYR48 . 48".
        value = re.sub(
            r"(?<=\d)\s*\.\s*(?=\d{2}\b)",
            ".",
            value,
        )

        return value


    @classmethod
    def _price_from_locator(
        cls,
        locator,
    ) -> str:

        # 1. Amazon's hidden accessible value is normally the safest.
        try:
            offscreen = locator.locator(
                ".a-offscreen"
            ).first

            if offscreen.count():
                value = (
                    offscreen.inner_text(
                        timeout=1500
                    )
                    .strip()
                )

                value = cls._normalise_price_text(
                    value
                )

                if (
                    value
                    and re.search(
                        r"\d",
                        value,
                    )
                    and not re.fullmatch(
                        r"\d+\.",
                        value,
                    )
                ):
                    return value

        except Exception:
            pass

        # 2. aria-label can contain the complete spoken price.
        try:
            aria = locator.get_attribute(
                "aria-label"
            )

            aria = cls._normalise_price_text(
                aria or ""
            )

            if (
                aria
                and re.search(
                    r"\d",
                    aria,
                )
            ):
                return aria

        except Exception:
            pass

        # 3. Reconstruct from visible symbol / whole / fraction.
        try:
            symbol = ""
            whole = ""
            fraction = ""

            symbol_locator = locator.locator(
                ".a-price-symbol"
            ).first

            if symbol_locator.count():
                symbol = (
                    symbol_locator.inner_text(
                        timeout=1000
                    )
                    .strip()
                )

            whole_locator = locator.locator(
                ".a-price-whole"
            ).first

            if whole_locator.count():
                whole = (
                    whole_locator.inner_text(
                        timeout=1000
                    )
                    .strip()
                )

            fraction_locator = locator.locator(
                ".a-price-fraction"
            ).first

            if fraction_locator.count():
                fraction = (
                    fraction_locator.inner_text(
                        timeout=1000
                    )
                    .strip()
                )

            whole = re.sub(
                r"[^0-9,]",
                "",
                whole,
            )

            fraction = re.sub(
                r"[^0-9]",
                "",
                fraction,
            )

            if whole:
                number = whole

                if fraction:
                    number += "." + fraction[:2]

                if symbol:
                    return cls._normalise_price_text(
                        f"{symbol} {number}"
                    )

                # The visible text on the price container may carry
                # a currency code such as MYR even when the symbol
                # child does not.
                try:
                    container_text = (
                        locator.inner_text(
                            timeout=1200
                        )
                        .strip()
                    )
                except Exception:
                    container_text = ""

                container_text = (
                    cls._normalise_price_text(
                        container_text
                    )
                )

                currency_match = re.search(
                    r"\b(MYR|GBP|USD|SGD|AUD)\b",
                    container_text,
                    flags=re.IGNORECASE,
                )

                if currency_match:
                    return (
                        f"{currency_match.group(1).upper()} "
                        f"{number}"
                    )

                return number

        except Exception:
            pass

        # 4. Last local fallback: use the price container's own text.
        try:
            value = (
                locator.inner_text(
                    timeout=1500
                )
                .strip()
            )

            return cls._normalise_price_text(
                value
            )

        except Exception:
            return ""


    @classmethod
    def _price_from_offer_locator(
        cls,
        offer,
    ) -> str:

        for selector in (
            ".a-price",
            ".olpOfferPrice",
        ):
            try:
                locator = offer.locator(
                    selector
                ).first

                if not locator.count():
                    continue

                value = cls._price_from_locator(
                    locator
                )

                if value:
                    return value

            except Exception:
                continue

        return ""


    def _delivery_from_offer_text(
        self,
        offer_text: str,
    ) -> str:

        text = self._normalise_price_text(
            offer_text
        )

        if not text:
            return ""

        lower = text.lower()

        # UK first-order promotions are not Malaysian shipping.
        if (
            self.target_market == "MY"
            and (
                "on your first order to uk or ireland"
                in lower
                or "on your first order to the uk or ireland"
                in lower
            )
        ):
            # There may still be an explicit paid MYR delivery
            # charge elsewhere in the same offer; look for that
            # before discarding the promotion.
            pass

        # Explicit paid delivery, e.g.
        # "MYR 76.87 delivery 9 - 12 September"
        paid_match = re.search(
            r"((?:MYR|RM|GBP|USD|SGD|AUD|£|US\$|S\$|A\$|\$)"
            r"\s*[0-9][0-9,]*(?:\.[0-9]{1,2})?"
            r"\s+delivery\b[^.]*\.?)",
            text,
            flags=re.IGNORECASE,
        )

        if paid_match:
            return paid_match.group(1).strip()

        # Threshold-based free delivery is conditional.
        conditional_match = re.search(
            r"(FREE delivery[^.]*"
            r"(?:eligible orders over|orders over|qualifying orders|minimum order|"
            r"if you spend|when you spend|spend at least)"
            r"[^.]*\.?)",
            text,
            flags=re.IGNORECASE,
        )

        if conditional_match:
            threshold = re.search(
                r"(MYR|RM|GBP|USD|SGD|AUD|£|US\$|S\$|A\$|\$)\s*"
                r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
                conditional_match.group(1),
                flags=re.IGNORECASE,
            )

            if threshold:
                return (
                    "Conditional free delivery over "
                    f"{threshold.group(1)} "
                    f"{threshold.group(2)}"
                )

            return "Conditional free delivery"

        # UK/Ireland first-order promotion: not applicable to MY.
        if (
            self.target_market == "MY"
            and (
                "on your first order to uk or ireland"
                in lower
                or "on your first order to the uk or ireland"
                in lower
            )
        ):
            return ""

        # Genuine explicit free-delivery message in the offer.
        free_match = re.search(
            r"(FREE delivery[^.]*\.?)",
            text,
            flags=re.IGNORECASE,
        )

        if free_match:
            return free_match.group(1).strip()

        return ""


    @staticmethod

    def _text_from_locator_selectors(

        locator,

        selectors: list[str],

    ) -> str:

        for selector in selectors:

            try:

                child = locator.locator(selector).first

                if not child.count():

                    continue

                value = child.inner_text(

                    timeout=2000

                ).strip()

                if value:

                    return value

            except Exception:

                continue

        return ""



    @staticmethod

    def _condition_from_text(

        text: str,

    ) -> str:

        lower = text.lower()

        used_match = re.search(

            r"\bused\s*[-–—:]?\s*"

            r"(like new|very good|good|acceptable)?",

            lower,

        )

        if used_match:

            detail = (used_match.group(1) or "").strip()

            return (

                f"Used - {detail.title()}"

                if detail

                else "Used"

            )

        if "collectible" in lower:

            return "Collectible"

        if "renewed" in lower:

            return "Renewed"

        if re.search(r"\bnew\b", lower):

            return "New"

        return ""



    @staticmethod

    def _seller_from_offer_locator(

        offer,

    ) -> str:

        for selector in (

            "#aod-offer-soldBy a",

            "#aod-offer-soldBy",

            ".aod-offer-soldBy a",

            ".aod-offer-soldBy",

        ):

            try:

                locator = offer.locator(selector).first

                if not locator.count():

                    continue

                value = locator.inner_text(

                    timeout=2000

                ).strip()

                if value:

                    value = re.sub(

                        r"^Sold by\s+",

                        "",

                        value,

                        flags=re.IGNORECASE,

                    ).strip()

                    return value[:80]

            except Exception:

                continue

        return ""



    def _delivery_from_offer_locator(

        self,

        offer,

    ) -> str:

        chunks = []

        for selector in (

            "#aod-offer-shipsFrom",

            ".aod-offer-shipsFrom",

            "#aod-offer-delivery",

            ".aod-offer-delivery",

        ):

            try:

                locators = offer.locator(selector)

                for index in range(min(locators.count(), 6)):

                    value = locators.nth(index).inner_text(

                        timeout=1500

                    ).strip()

                    if value and value not in chunks:

                        chunks.append(value)

            except Exception:

                continue

        combined = re.sub(

            r"\s+",

            " ",

            " ".join(chunks),

        ).strip()

        if not combined:

            return ""

        lower = combined.lower()

        if (

            self.target_market == "MY"

            and (

                "to uk or ireland" in lower

                or "to the uk or ireland" in lower

            )

        ):

            return ""

        if (

            "free delivery" in lower

            and any(

                marker in lower

                for marker in (

                    "eligible orders over",

                    "orders over",

                    "qualifying orders",

                    "minimum order",

                    "if you spend",

                    "when you spend",

                    "spend at least",

                )

            )

        ):

            return "Conditional free delivery"

        return combined[:250]



    # Primary Amazon offer helpers

    # -----------------------------------------------------

    @staticmethod

    def _text_and_selector(

        page,

        selectors: list[str],

    ) -> tuple[str, str]:

        for selector in selectors:

            try:

                locator = page.locator(

                    selector

                ).first

                if not locator.count():

                    continue

                text = (

                    locator.inner_text(

                        timeout=2000

                    )

                    .strip()

                )

                if text:

                    return (

                        text,

                        selector,

                    )

            except Exception:

                continue

        return (

            "",

            "",

        )



    @staticmethod

    def _extract_primary_condition(

        page,

    ) -> str:

        # Restrict condition detection to the main purchasing

        # area. This prevents "Used" text from recommendations,

        # reviews or "other sellers" elsewhere on the page from

        # being attached to the selected offer.

        selectors = [

            "#desktop_buybox",

            "#buybox",

            "#rightCol",

        ]

        text = ""

        for selector in selectors:

            try:

                locator = page.locator(

                    selector

                ).first

                if locator.count():

                    candidate = (

                        locator.inner_text(

                            timeout=2500

                        )

                        .strip()

                    )

                    if candidate:

                        text = candidate

                        break

            except Exception:

                continue

        lower = text.lower()

        used_match = re.search(

            r"\bused\s*[-–—:]?\s*"

            r"(like new|very good|good|acceptable)?",

            lower,

        )

        if used_match:

            detail = (

                used_match.group(1)

                or ""

            ).strip()

            if detail:

                return (

                    "Used - "

                    + detail.title()

                )

            return "Used"

        if "collectible" in lower:

            return "Collectible"

        if "renewed" in lower:

            return "Renewed"

        # Amazon's normal product detail buy box is a new offer

        # unless it explicitly labels the selected offer otherwise.

        return "New"



    @staticmethod

    def _extract_primary_seller(

        page,

    ) -> str:

        selectors = [

            "#merchant-info",

            "#sellerProfileTriggerId",

            "#tabular-buybox-truncate-1",

            "#tabular-buybox-truncate-0",

        ]

        chunks = []

        for selector in selectors:

            try:

                locator = page.locator(

                    selector

                ).first

                if not locator.count():

                    continue

                value = (

                    locator.inner_text(

                        timeout=2000

                    )

                    .strip()

                )

                if (

                    value

                    and value not in chunks

                ):

                    chunks.append(

                        value

                    )

            except Exception:

                continue

        if not chunks:

            return ""

        combined = " ".join(

            chunks

        )

        combined = re.sub(

            r"\s+",

            " ",

            combined,

        ).strip()

        sold_by = re.search(

            r"Sold by\s+(.+?)(?:\s+and\s+|\s+Ships from\s+|$)",

            combined,

            flags=re.IGNORECASE,

        )

        if sold_by:

            seller = sold_by.group(1).strip()

            if seller:

                return seller[:80]

        # Some page layouts expose the seller name without

        # the "Sold by" label.

        if len(combined) <= 80:

            return combined

        return ""



    def _extract_primary_delivery(

        self,

        page,

    ) -> tuple[str, str]:

        # Use only selectors associated with the selected main

        # offer. Deliberately avoid the broad

        # #mir-layout-DELIVERY_BLOCK container because it can

        # include unrelated promotions or alternative offers.

        selectors = [

            "#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE",

            "#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE span",

            "#deliveryBlockMessage",

            "#delivery-message",

        ]

        text, selector = self._text_and_selector(

            page,

            selectors,

        )

        if not text:

            return (

                "",

                "",

            )

        normalised = re.sub(

            r"\s+",

            " ",

            text,

        ).strip()

        lower = normalised.lower()

        # A UK first-order promotion must never be reported as

        # shipping for a Malaysian purchase.

        if (

            self.target_market == "MY"

            and (

                "to uk or ireland" in lower

                or "to the uk or ireland" in lower

            )

        ):

            return (

                "",

                selector,

            )

        # Amazon often advertises "FREE delivery" only when an

        # order passes a threshold. Preserve the condition

        # instead of presenting it as zero-cost shipping.

        conditional_markers = [

            "eligible orders over",

            "orders over",

            "qualifying orders",

            "minimum order",

            "if you spend",

            "when you spend",

            "spend at least",

        ]

        if (

            "free delivery" in lower

            and any(

                marker in lower

                for marker in conditional_markers

            )

        ):

            threshold = re.search(

                r"(MYR|RM|GBP|USD|SGD|AUD|£|US\\$|S\\$|A\\$|\\$)\\s*"

                r"([0-9][0-9,]*(?:\\.[0-9]{1,2})?)",

                normalised,

                flags=re.IGNORECASE,

            )

            if threshold:

                return (

                    "Conditional free delivery "

                    f"over {threshold.group(1)} "

                    f"{threshold.group(2)}",

                    selector,

                )

            return (

                "Conditional free delivery",

                selector,

            )

        return (

            normalised,

            selector,

        )



    # -----------------------------------------------------

    # Currency detection

    # -----------------------------------------------------

    def _detect_currency(

        self,

        text: str,

    ) -> str:

        value = (

            text.upper()

            .replace("\xa0", " ")

        )

        if (

            "MYR" in value

            or "RM " in value

        ):

            return "MYR"

        if (

            "GBP" in value

            or "£" in text

        ):

            return "GBP"

        if (

            "USD" in value

            or "US$" in value

        ):

            return "USD"

        if (

            "SGD" in value

            or "S$" in value

        ):

            return "SGD"

        if (

            "AUD" in value

            or "A$" in value

        ):

            return "AUD"

        if "$" in text:

            return self._active_currency

        return self._active_currency

















    # -----------------------------------------------------

    # Page helpers

    # -----------------------------------------------------

    @staticmethod

    def _settle_page(

        page,

    ):

        try:

            page.wait_for_load_state(

                "networkidle",

                timeout=4000,

            )

        except PlaywrightTimeoutError:

            pass

















    @staticmethod

    def _is_blocked(

        page,

    ) -> bool:

        try:

            text = (

                page.locator("body")

                .inner_text(

                    timeout=5000

                )

                .lower()

            )

        except Exception:

            return True

        blocked_phrases = [

            "enter the characters you see below",

            "sorry, we just need to make sure",

            "robot check",

            "captcha",

        ]

        return any(

            phrase in text

            for phrase in blocked_phrases

        )

















    @staticmethod

    def _text_from_selectors(

        page,

        selectors: list[str],

    ) -> str:

        for selector in selectors:

            try:

                locator = (

                    page.locator(

                        selector

                    )

                    .first

                )

                if locator.count():

                    text = (

                        locator.inner_text(

                            timeout=2000

                        )

                        .strip()

                    )

                    if text:

                        return text

            except Exception:

                continue

        return ""

















    # -----------------------------------------------------

    # ISBN conversion

    # -----------------------------------------------------

    @staticmethod

    def _isbn13_to_isbn10(

        isbn: str,

    ) -> str:

        digits = re.sub(

            r"[^0-9]",

            "",

            isbn,

        )

        if (

            len(digits) != 13

            or not digits.startswith("978")

        ):

            return ""

        base = digits[3:12]

        total = sum(

            (10 - index) * int(digit)

            for index, digit

            in enumerate(base)

        )

        check_value = (

            11 - (total % 11)

        ) % 11

        check_digit = (

            "X"

            if check_value == 10

            else str(check_value)

        )

        return (

            base

            + check_digit

        )

















    # -----------------------------------------------------

    # ISBN extraction

    # -----------------------------------------------------

    @staticmethod

    def _extract_isbn13(

        text: str,

    ) -> str:

        patterns = [

            (

                r"ISBN-13\s*[:\n]\s*"

                r"([0-9\-\s]{13,20})"

            ),

            (

                r"ISBN 13\s*[:\n]\s*"

                r"([0-9\-\s]{13,20})"

            ),

        ]

        for pattern in patterns:

            match = re.search(

                pattern,

                text,

                flags=re.IGNORECASE,

            )

            if not match:

                continue

            isbn = re.sub(

                r"[^0-9]",

                "",

                match.group(1),

            )

            if len(isbn) == 13:

                return isbn

        return ""

















    # -----------------------------------------------------

    # Price

    # -----------------------------------------------------

    @staticmethod

    def _parse_price(

        value: str,

    ) -> Decimal | None:

        if not value:

            return None

        cleaned = (

            value

            .replace(",", "")

            .strip()

        )

        match = re.search(

            r"([0-9]+(?:\.[0-9]{1,2})?)",

            cleaned,

        )

        if not match:

            return None

        try:

            return Decimal(

                match.group(1)

            )

        except Exception:

            return None

















    # -----------------------------------------------------

    # Availability

    # -----------------------------------------------------

    @staticmethod

    def _parse_availability(

        text: str,

        price: Decimal | None,

        delivery_text: str = "",

    ) -> bool:

        lower = (

            text

            .lower()

            .strip()

        )

        delivery_lower = (

            delivery_text

            .lower()

            .strip()

        )

        # ---------------------------------------------

        # Cannot be delivered to selected destination

        # ---------------------------------------------

        cannot_ship = [

            (

                "cannot be shipped to your "

                "selected delivery location"

            ),

            (

                "can't be shipped to your "

                "selected delivery location"

            ),

            "cannot be delivered to your location",

            "does not ship to your location",

            "not available for delivery to",

        ]

        if any(

            phrase in delivery_lower

            for phrase in cannot_ship

        ):

            return False

        # ---------------------------------------------

        # Product availability

        # ---------------------------------------------

        # Amazon sometimes allows an item to be ordered even though it
        # is temporarily out of stock. In that case it remains
        # purchasable, although Amazon cannot yet give a delivery date.
        if (
            "temporarily out of stock" in lower
            and "order now" in lower
            and "deliver when available" in lower
        ):
            return True

        unavailable = [

            "currently unavailable",

            "temporarily out of stock",

            "unavailable",

            "out of stock",

        ]

        if any(

            phrase in lower

            for phrase in unavailable

        ):

            return False

        available = [

            "in stock",

            "only ",

            "usually dispatched",

            "usually ships",

        ]

        if any(

            phrase in lower

            for phrase in available

        ):

            return True

        # Amazon sometimes provides a valid

        # purchasable price without useful

        # availability wording.

        return price is not None

















    # -----------------------------------------------------

    # Format

    # -----------------------------------------------------

    @staticmethod

    def _extract_format(

        text: str,

    ) -> str:

        formats = [

            "Paperback",

            "Hardcover",

            "Hardback",

            "Board book",

            "Mass Market Paperback",

        ]

        lower = text.lower()

        for format_name in formats:

            if (

                format_name.lower()

                in lower

            ):

                return format_name

        return ""

















    # -----------------------------------------------------

    # macOS window handling

    # -----------------------------------------------------

    @classmethod

    def _minimise_browser_repeatedly(

        cls,

    ):

        # Chrome windows can appear/reappear at different

        # points while Playwright creates pages and navigates.

        # Keep catching them for several seconds.

        for _ in range(24):

            time.sleep(0.25)

            cls._minimise_browser()









    @staticmethod

    def _minimise_browser():

        script = '''

        tell application "System Events"

            repeat with p in (every process whose name is "Google Chrome for Testing")

                repeat with w in windows of p

                    try

                        set value of attribute "AXMinimized" of w to true

                    end try

                end repeat

            end repeat

        end tell

        '''

        result = subprocess.run(

            [

                "osascript",

                "-e",

                script,

            ],

            check=False,

            capture_output=True,

            text=True,

        )

        if result.returncode != 0:

            print(

                "Chrome minimise failed:",

                result.stderr.strip(),

            )









    # -----------------------------------------------------

    # Batch shutdown

    # -----------------------------------------------------

    def shutdown_browser(

        self,

    ):

        self._shutdown_requested = True

        thread = self._browser_thread

        if (

            thread is not None

            and thread.is_alive()

        ):

            self._browser_queue.put(

                (

                    "shutdown",

                    None,

                    None,

                )

            )

            thread.join(

                timeout=10

            )

        self._browser_thread = None