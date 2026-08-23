import queue

import re

import threading

import time

from concurrent.futures import Future

from decimal import Decimal

import subprocess

from playwright.sync_api import (

    TimeoutError as PlaywrightTimeoutError,

    sync_playwright,

)

from core.health import SupplierCapabilities

from core.models import Offer

from suppliers.base import Supplier

from suppliers.profile import (

    AffiliateProfile,

    ConnectorType,

    SupplierProfile,

    SupplierScope,

)



class KinokuniyaMalaysiaSupplier(Supplier):

    name = "Kinokuniya Malaysia"

    capabilities = SupplierCapabilities(

        price=True,

        availability=True,

        stock_quantity=False,

        delivery=True,

        publisher=True,

        format=True,

    )

    profile = SupplierProfile(

        display_name="Kinokuniya Malaysia",

        home_country="JP",

        market="MY",

        operating_markets=("MY",),

        scope=SupplierScope.INTERNATIONAL,

        independent=False,

        marketplace=False,

        institutional=True,

        shipping_countries=("MY",),

        global_shipping=False,

        connector_type=ConnectorType.WEBSITE,

        affiliate=AffiliateProfile(

            available=True,

            network="Involve Asia",

            commission="~4%",

            cookie_days=30,

        ),

    )

    BASE_URL = (

        "https://malaysia.kinokuniya.com/bw/"

    )

    # -----------------------------------------------------

    # Shared browser worker

    # -----------------------------------------------------

    _browser_queue = queue.Queue()

    _browser_thread = None

    _browser_thread_lock = (

        threading.Lock()

    )

    _shutdown_requested = False



    def __init__(self):

        # Do not start Chromium when the module

        # imports. Start it only when Kinokuniya

        # is actually queried.

        pass



    # -----------------------------------------------------

    # Public lookup

    # -----------------------------------------------------

    def lookup(

        self,

        isbn: str,

    ) -> list[Offer]:

        url = (

            f"{self.BASE_URL}{isbn}"

        )

        try:

            page_text = (

                self._request_page(

                    url

                )

            )

        except Exception as exc:

            print(

                "Kinokuniya browser lookup "

                f"failed for {isbn}: "

                f"{exc}"

            )

            return []



        if not page_text:

            return []



        # -------------------------------------------------

        # Verify ISBN

        # -------------------------------------------------

        page_isbn = (

            self._extract_isbn(

                page_text

            )

        )

        if (

            page_isbn

            and page_isbn != isbn

        ):

            print(

                "Kinokuniya ISBN mismatch: "

                f"requested {isbn}, "

                f"page returned "

                f"{page_isbn}"

            )

            return []



        # -------------------------------------------------

        # Extract offer information

        # -------------------------------------------------

        title = (

            self._extract_title(

                page_text

            )

        )

        price = (

            self._extract_price(

                page_text

            )

        )

        available = (

            self._extract_availability(

                page_text

            )

        )

        (

            delivery_min_days,

            delivery_max_days,

            delivery_text,

        ) = self._extract_delivery(

            page_text

        )

        publisher = (

            self._extract_publisher(

                page_text

            )

        )

        format_name = (

            self._extract_format(

                page_text

            )

        )



        # -------------------------------------------------

        # Detect a non-product / failed page

        # -------------------------------------------------

        if (

            not page_isbn

            and price is None

        ):

            print(

                "Kinokuniya product "

                f"not found: {isbn}"

            )

            return []



        # -------------------------------------------------

        # Build offer

        # -------------------------------------------------

        return [

            Offer(

                isbn=isbn,

                supplier=self.name,

                title=title,

                price=price,

                currency="MYR",

                available=available,

                offer_type="",

                rrp=None,

                stock_quantity=None,

                delivery_min_days=(

                    delivery_min_days

                ),

                delivery_max_days=(

                    delivery_max_days

                ),

                delivery_text=(

                    delivery_text

                ),

                publisher=publisher,

                format=format_name,

                url=url,

            )

        ]



    # -----------------------------------------------------

    # Browser request interface

    # -----------------------------------------------------

    @classmethod

    def _request_page(

        cls,

        url: str,

    ) -> str:

        cls._ensure_browser_worker()

        future = Future()

        cls._browser_queue.put(

            (

                "lookup",

                url,

                future,

            )

        )

        # The caller waits for the browser

        # worker to complete this particular

        # Kinokuniya request.

        return future.result()



    @classmethod

    def _ensure_browser_worker(

        cls,

    ):

        with cls._browser_thread_lock:

            if (

                cls._browser_thread

                is not None

                and cls._browser_thread.is_alive()

            ):

                return



            cls._shutdown_requested = (

                False

            )



            cls._browser_thread = (

                threading.Thread(

                    target=(

                        cls._browser_worker

                    ),

                    name=(

                        "KinokuniyaBrowser"

                    ),

                    daemon=True,

                )

            )

            cls._browser_thread.start()



    # -----------------------------------------------------

    # Minimise Browser

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

    # Browser worker

    # -----------------------------------------------------

    @classmethod
    def _browser_worker(
        cls,
    ):

        print(
            "Kinokuniya browser "
            "worker starting..."
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
                    locale="en-GB",
                    viewport={
                        "width": 320,
                        "height": 240,
                    },
                )
            )

            page = (
                context.new_page()
            )

            print(
                "Kinokuniya browser ready."
            )

            first_navigation = True

            while not cls._shutdown_requested:

                try:

                    job = (
                        cls._browser_queue
                        .get(
                            timeout=1
                        )
                    )

                except queue.Empty:
                    continue

                if not job:
                    continue

                action = job[0]

                if action == "shutdown":
                    cls._browser_queue.task_done()
                    break

                if action != "lookup":
                    cls._browser_queue.task_done()
                    continue

                _, url, future = job

                try:

                    text_value = (
                        cls._load_page_in_browser(
                            page,
                            url,
                        )
                    )

                    if first_navigation:
                        cls._minimise_browser_repeatedly()
                        first_navigation = False

                    future.set_result(
                        text_value
                    )

                except Exception as exc:

                    future.set_exception(
                        exc
                    )

                finally:

                    cls._browser_queue.task_done()

        except Exception as exc:

            print(
                "Kinokuniya browser "
                f"worker failed: {exc}"
            )

            # Fail anything already waiting in the queue
            # instead of leaving callers hanging forever.
            while True:

                try:

                    job = (
                        cls._browser_queue
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

                cls._browser_queue.task_done()

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
                "Kinokuniya browser "
                "worker stopped."
            )


    # -----------------------------------------------------

    # Load one product page

    # -----------------------------------------------------

    @staticmethod
    def _load_page_in_browser(
        page,
        url: str,
    ) -> str:

        response = page.goto(
            url,
            wait_until=(
                "domcontentloaded"
            ),
            timeout=30000,
        )

        if response is not None:

            print(
                "Kinokuniya HTTP:",
                response.status,
                url,
            )

        # Give any remaining page scripts
        # a brief chance to complete, but
        # don't fail merely because some
        # background request remains active.
        try:

            page.wait_for_load_state(
                "networkidle",
                timeout=4000,
            )

        except PlaywrightTimeoutError:
            pass

        body = page.locator(
            "body"
        )

        return body.inner_text(
            timeout=10000
        )


    # -----------------------------------------------------

    # Shutdown

    # -----------------------------------------------------

    @classmethod
    def shutdown_browser(
        cls,
    ):

        cls._shutdown_requested = True

        thread = cls._browser_thread

        if (
            thread is not None
            and thread.is_alive()
        ):

            cls._browser_queue.put(
                (
                    "shutdown",
                    None,
                    None,
                )
            )

            # Wait briefly for Playwright to close
            # the page, context and Chromium cleanly.
            thread.join(
                timeout=10
            )

        cls._browser_thread = None


    # -----------------------------------------------------

    # Parsing helpers

    # -----------------------------------------------------

    @staticmethod

    def _extract_isbn(

        text: str,

    ) -> str:

        match = re.search(

            r"\bISBN\s+"

            r"([0-9Xx\- ]{10,20})",

            text,

            flags=re.IGNORECASE,

        )



        if not match:

            return ""



        return re.sub(

            r"[^0-9Xx]",

            "",

            match.group(1),

        )



    @staticmethod

    def _extract_title(

        text: str,

    ) -> str:

        match = re.search(

            r"English Books\s+"

            r"(.+?)\s+"

            r"by\s+",

            text,

            flags=(

                re.IGNORECASE

                | re.DOTALL

            ),

        )



        if not match:

            return ""



        return re.sub(

            r"\s+",

            " ",

            match.group(1),

        ).strip()



    @staticmethod

    def _extract_price(

        text: str,

    ) -> Decimal | None:

        match = re.search(

            r"RM\s*"

            r"([0-9,]+\.\d{2})"

            r"\s+Online Price",

            text,

            flags=re.IGNORECASE,

        )



        if not match:

            return None



        value = (

            match.group(1)

            .replace(",", "")

        )



        try:

            return Decimal(

                value

            )

        except Exception:

            return None



    @staticmethod

    def _extract_availability(

        text: str,

    ) -> bool:

        lower = text.lower()



        unavailable_phrases = [

            (

                "availability status : "

                "out of stock"

            ),

            (

                "availability status: "

                "out of stock"

            ),

            "currently unavailable",

            "not available",

            "sold out",

        ]



        for phrase in (

            unavailable_phrases

        ):

            if phrase in lower:

                return False



        available_phrases = [

            (

                "availability status : "

                "in stock"

            ),

            (

                "availability status: "

                "in stock"

            ),

            (

                "in stock at the "

                "fulfilment centre"

            ),

            (

                "store stock status "

                "in stock"

            ),

            "usually dispatches around",

            "add to cart",

            "add to basket",

        ]



        for phrase in (

            available_phrases

        ):

            if phrase in lower:

                return True



        return False



    @staticmethod

    def _extract_delivery(

        text: str,

    ) -> tuple[

        int | None,

        int | None,

        str,

    ]:

        range_match = re.search(

            r"Usually dispatches around\s+"

            r"(\d+)\s+to\s+(\d+)"

            r"\s+working days",

            text,

            flags=re.IGNORECASE,

        )



        if range_match:

            minimum = int(

                range_match.group(1)

            )

            maximum = int(

                range_match.group(2)

            )



            return (

                minimum,

                maximum,

                (

                    f"{minimum} to "

                    f"{maximum} "

                    "working days"

                ),

            )



        single_match = re.search(

            r"Usually dispatches around\s+"

            r"(\d+)\s+working days?",

            text,

            flags=re.IGNORECASE,

        )



        if single_match:

            days = int(

                single_match.group(1)

            )



            return (

                days,

                days,

                f"{days} working days",

            )



        return (

            None,

            None,

            "",

        )



    @staticmethod

    def _extract_publisher(

        text: str,

    ) -> str:

        match = re.search(

            r"\bPublisher\s+"

            r"(.+?)\s+"

            r"ISBN\b",

            text,

            flags=(

                re.IGNORECASE

                | re.DOTALL

            ),

        )



        if not match:

            return ""



        return re.sub(

            r"\s+",

            " ",

            match.group(1),

        ).strip()



    @staticmethod

    def _extract_format(

        text: str,

    ) -> str:

        match = re.search(

            r"Item Type\s+"

            r".+?"

            r"\(([^)]+)\)",

            text,

            flags=re.IGNORECASE,

        )



        if not match:

            return ""



        return (

            match.group(1)

            .strip()

        )
