from pathlib import Path
import logging
import re
import time

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from bibliography.google_books import GoogleBooksProvider
from bibliography.open_library import OpenLibraryProvider
from bibliography.service import BibliographyService

from core.comparison import cheapest_offer, comparison_price_myr
from core.config import settings
from core.logging_config import configure_logging
from core.isbn import validate_isbn
from core.search_jobs import SearchJob, SearchQueue
from core.sourcing import SourcingEngine

from suppliers.bookxcess import BookXcessSupplier
from suppliers.bookdelivery import BookDeliverySupplier
from suppliers.mph import MPHSupplier
from suppliers.litbooks import LitBooksSupplier
from suppliers.kinokuniya_MY import KinokuniyaMalaysiaSupplier
from suppliers.amazon_uk import AmazonUKSupplier
from suppliers.amazon_us import AmazonUSSupplier


configure_logging()
logger = logging.getLogger("booksourcing.web")

app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    debug=settings.debug,
)


@app.middleware("http")
async def log_requests(
    request: Request,
    call_next,
):
    started = time.perf_counter()

    try:
        response = await call_next(
            request
        )
    except Exception:
        logger.exception(
            "Unhandled request error | %s %s",
            request.method,
            request.url.path,
        )
        raise

    duration_ms = (
        time.perf_counter() - started
    ) * 1000

    logger.info(
        "%s %s -> %s (%.0f ms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )

    return response

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates")
)


# ---------------------------------------------------------
# Markets
# ---------------------------------------------------------

MARKETS = {
    "MY": {"name": "Malaysia", "currency": "MYR"},
    "SG": {"name": "Singapore", "currency": "SGD"},
    "GB": {"name": "United Kingdom", "currency": "GBP"},
    "US": {"name": "United States", "currency": "USD"},
    "AU": {"name": "Australia", "currency": "AUD"},
}


# ---------------------------------------------------------
# Supplier registry
#
# IMPORTANT: keep supplier CLASSES here, not live instances.
# Each queued search receives fresh connector instances.
# ---------------------------------------------------------

ALL_SUPPLIER_CLASSES = [
    BookXcessSupplier,
    BookDeliverySupplier,
    MPHSupplier,
    LitBooksSupplier,
    KinokuniyaMalaysiaSupplier,
    AmazonUKSupplier,
    AmazonUSSupplier,
]

SUPPLIER_CLASSES = (
    ALL_SUPPLIER_CLASSES
    if settings.enable_live_suppliers
    else []
)


def new_supplier_instances():
    return [supplier_class() for supplier_class in SUPPLIER_CLASSES]


# These lightweight instances are only used for UI/profile data.
# They never run supplier lookups or own a browser session.
PROFILE_SUPPLIERS = new_supplier_instances()


# ---------------------------------------------------------
# Bibliographic metadata
# ---------------------------------------------------------

bibliography = BibliographyService(
    providers=[
        GoogleBooksProvider(),
        OpenLibraryProvider(),
    ]
)


# ---------------------------------------------------------
# Supplier helpers
# ---------------------------------------------------------

def suppliers_for_market(market: str, suppliers=None):
    source = suppliers if suppliers is not None else PROFILE_SUPPLIERS

    return [
        supplier
        for supplier in source
        if supplier.profile.relevant_to(market)
    ]


def supplier_labels(supplier, market: str) -> list[str]:
    profile = supplier.profile

    # Describe scope from the user's selected market.
    if profile.home_country == market:
        scope_label = "National"
    else:
        scope_label = "International"

    labels = [scope_label]

    if profile.independent:
        labels.append("Independent")

    if profile.institutional:
        labels.append("Institutional")

    if profile.marketplace:
        labels.append("Marketplace")

    return labels


def build_supplier_catalog():
    catalog = {}

    for market_code in MARKETS:
        catalog[market_code] = []

        for supplier in suppliers_for_market(market_code):
            catalog[market_code].append(
                {
                    "name": supplier.name,
                    "display_name": supplier.profile.display_name,
                    "labels": supplier_labels(supplier, market_code),
                }
            )

    return catalog


SUPPLIER_CATALOG = build_supplier_catalog()


# ---------------------------------------------------------
# ISBN input parsing
# ---------------------------------------------------------

def parse_isbn_input(isbn_text: str) -> list[dict]:
    items = []

    for line in isbn_text.splitlines():
        raw_isbn = line.strip()

        if not raw_isbn:
            continue

        validation = validate_isbn(raw_isbn)

        items.append(
            {
                "raw_isbn": raw_isbn,
                "isbn": validation.isbn13 if validation.valid else raw_isbn,
                "quantity": 1,
                "valid": validation.valid,
                "validation_error": validation.error,
            }
        )

    return items


# ---------------------------------------------------------
# Result building
# ---------------------------------------------------------

def build_display_results(items: list[dict], sourcing_results):
    sourcing_by_isbn = {
        result.isbn: result
        for result in sourcing_results
    }

    results = []

    for item in items:
        if not item["valid"]:
            results.append(
                {
                    "isbn": item["raw_isbn"],
                    "quantity": item["quantity"],
                    "title": "",
                    "authors": "",
                    "metadata_source": "",
                    "publisher": "",
                    "year_published": "",
                    "book_format": "",
                    "series": "",
                    "series_number": "",
                    "offers": {},
                    "best": None,
                    "saving": None,
                    "best_total": None,
                    "best_landed_myr": None,
                    "total_saving": None,
                    "valid": False,
                    "validation_error": item["validation_error"],
                }
            )
            continue

        # Bibliographic metadata remains inside the queued job.
        metadata = bibliography.lookup(item["isbn"])

        title = ""
        authors = ""
        metadata_source = ""

        publisher = ""
        year_published = ""
        book_format = ""
        series = ""
        series_number = ""

        if metadata:
            title = metadata.title
            authors = ", ".join(metadata.authors)
            metadata_source = metadata.source

            publisher = getattr(
                metadata,
                "publisher",
                "",
            ) or ""

            published_value = (
                getattr(metadata, "published_date", "")
                or getattr(metadata, "publication_date", "")
                or getattr(metadata, "published_year", "")
                or getattr(metadata, "year", "")
                or ""
            )

            published_text = str(
                published_value
            ).strip()

            year_match = re.search(
                r"\b(1[5-9]\d{2}|20\d{2}|21\d{2})\b",
                published_text,
            )

            if year_match:
                year_published = year_match.group(1)

            book_format = (
                getattr(metadata, "format", "")
                or getattr(metadata, "binding", "")
                or ""
            )

            series = (
                getattr(metadata, "series", "")
                or getattr(metadata, "series_name", "")
                or ""
            )

            series_number = (
                getattr(metadata, "series_number", "")
                or ""
            )

        result = sourcing_by_isbn.get(item["isbn"])

        if result is None:
            results.append(
                {
                    "isbn": item["isbn"],
                    "quantity": item["quantity"],
                    "title": title,
                    "authors": authors,
                    "metadata_source": metadata_source,
                    "publisher": publisher,
                    "year_published": year_published,
                    "book_format": book_format,
                    "series": series,
                    "series_number": series_number,
                    "offers": {},
                    "best": None,
                    "saving": None,
                    "best_total": None,
                    "best_landed_myr": None,
                    "total_saving": None,
                    "valid": True,
                    "validation_error": "",
                }
            )
            continue

        quantity = item["quantity"]

        best = cheapest_offer(
            result.offers,
            quantity=quantity,
        )

        offers_by_supplier = {}

        for offer in result.offers:
            offers_by_supplier.setdefault(
                offer.supplier,
                [],
            ).append(offer)

        priced_available_offers = sorted(
            [
                offer
                for offer in result.offers
                if (
                    comparison_price_myr(
                        offer
                    )
                    is not None
                    and (
                        offer.stock_quantity is None
                        or offer.stock_quantity >= quantity
                    )
                )
            ],
            key=lambda offer: (
                comparison_price_myr(
                    offer
                )
            ),
        )

        saving = None
        best_landed_myr = None

        if best:
            best_landed_myr = (
                comparison_price_myr(
                    best
                )
            )

            alternative_offers = [
                offer
                for offer
                in priced_available_offers
                if offer.supplier != best.supplier
            ]

            if alternative_offers:
                alternative = (
                    alternative_offers[0]
                )

                alternative_landed_myr = (
                    comparison_price_myr(
                        alternative
                    )
                )

                if (
                    best_landed_myr is not None
                    and alternative_landed_myr is not None
                ):
                    saving = (
                        alternative_landed_myr
                        - best_landed_myr
                    )

        best_total = None
        total_saving = None

        if best_landed_myr is not None:
            best_total = (
                best_landed_myr
                * quantity
            )

        if saving is not None:
            total_saving = (
                saving
                * quantity
            )

        if not title and result.offers:
            title = result.offers[0].title
            metadata_source = "Supplier fallback"

        results.append(
            {
                "isbn": result.isbn,
                "quantity": quantity,
                "title": title,
                "authors": authors,
                "metadata_source": metadata_source,
                "publisher": publisher,
                "year_published": year_published,
                "book_format": book_format,
                "series": series,
                "series_number": series_number,
                "offers": offers_by_supplier,
                "best": best,
                "saving": saving,
                "best_total": best_total,
                "best_landed_myr": best_landed_myr,
                "total_saving": total_saving,
                "valid": True,
                "validation_error": "",
            }
        )

    return results


# ---------------------------------------------------------
# Queue job execution
# ---------------------------------------------------------

def run_search_job(job: SearchJob):
    payload = job.payload

    isbn_text = payload["isbn_text"]
    market = payload["market"]
    requested_supplier_names = payload["supplier_names"]

    items = parse_isbn_input(isbn_text)

    valid_items = [item for item in items if item["valid"]]

    # Fresh supplier objects are private to this one queued job.
    all_job_suppliers = new_supplier_instances()

    available_suppliers = suppliers_for_market(
        market,
        all_job_suppliers,
    )

    allowed_suppliers = {
        supplier.name: supplier
        for supplier in available_suppliers
    }

    selected_suppliers = [
        allowed_suppliers[name]
        for name in requested_supplier_names
        if name in allowed_suppliers
    ]

    selected_supplier_names = [
        supplier.name
        for supplier in selected_suppliers
    ]

    target_currency = MARKETS[market]["currency"]

    for supplier in selected_suppliers:
        configure = getattr(
            supplier,
            "configure_for_market",
            None,
        )

        if callable(configure):
            configure(
                market=market,
                currency=target_currency,
            )

    total_checks = len(valid_items) * len(selected_suppliers)

    job.set_progress(
        0,
        total_checks,
        "Starting supplier search",
    )

    def progress_callback(
        completed: int,
        total: int,
        isbn: str,
        supplier_name: str,
    ):
        job.set_progress(
            completed,
            total,
            f"Checked {supplier_name} for {isbn}",
        )

    sourcing_results = []

    if selected_suppliers and valid_items:
        engine = SourcingEngine(
            suppliers=selected_suppliers,
            progress_callback=progress_callback,
        )

        sourcing_results = engine.lookup_many(
            [item["isbn"] for item in valid_items]
        )

    job.message = "Building book information"

    results = build_display_results(
        items,
        sourcing_results,
    )

    return {
        "results": results,
        "isbn_text": isbn_text,
        "selected_market": market,
        "selected_supplier_names": selected_supplier_names,
    }


SEARCH_QUEUE = SearchQueue(
    handler=run_search_job
)


# ---------------------------------------------------------
# Common template context
# ---------------------------------------------------------

def page_context(
    *,
    selected_market: str = "MY",
    isbn_text: str = "",
    selected_supplier_names=None,
    results=None,
    job: SearchJob | None = None,
):
    if selected_market not in MARKETS:
        selected_market = "MY"

    available_suppliers = suppliers_for_market(selected_market)

    if selected_supplier_names is None:
        selected_supplier_names = [
            supplier.name
            for supplier in available_suppliers
        ]

    selected_name_set = set(selected_supplier_names)

    active_suppliers = [
        supplier
        for supplier in available_suppliers
        if supplier.name in selected_name_set
    ]

    return {
        "results": results,
        "isbn_text": isbn_text,
        "selected_market": selected_market,
        "markets": MARKETS,
        "available_suppliers": available_suppliers,
        "active_suppliers": active_suppliers,
        "selected_supplier_names": selected_supplier_names,
        "supplier_catalog": SUPPLIER_CATALOG,
        "job": job,
        "job_status": job.status if job else None,
    }


# ---------------------------------------------------------
# Health check
# ---------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "environment": settings.environment,
        "version": settings.app_version,
        "live_suppliers_enabled": settings.enable_live_suppliers,
    }


# ---------------------------------------------------------
# Home page
# ---------------------------------------------------------

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context=page_context(),
    )


# ---------------------------------------------------------
# Submit search
#
# POST / remains for compatibility with the current HTML.
# It now queues the work and redirects immediately.
# ---------------------------------------------------------

@app.post("/")
def submit_search(
    isbn_text: str = Form(""),
    market: str = Form("MY"),
    supplier_names: list[str] = Form(default=[]),
):
    if market not in MARKETS:
        market = "MY"

    job = SEARCH_QUEUE.submit(
        {
            "isbn_text": isbn_text,
            "market": market,
            "supplier_names": supplier_names,
        }
    )

    return RedirectResponse(
        url=f"/search/{job.id}",
        status_code=303,
    )


# Clearer endpoint for the next HTML version.
@app.post("/search")
def submit_search_named(
    isbn_text: str = Form(""),
    market: str = Form("MY"),
    supplier_names: list[str] = Form(default=[]),
):
    if market not in MARKETS:
        market = "MY"

    job = SEARCH_QUEUE.submit(
        {
            "isbn_text": isbn_text,
            "market": market,
            "supplier_names": supplier_names,
        }
    )

    return RedirectResponse(
        url=f"/search/{job.id}",
        status_code=303,
    )


# ---------------------------------------------------------
# Search result / progress page
# ---------------------------------------------------------

@app.get("/search/{job_id}")
def search_page(
    job_id: str,
    request: Request,
):
    job = SEARCH_QUEUE.get(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Search job not found",
        )

    payload = job.payload

    if job.status == "complete" and job.result:
        result_data = job.result

        context = page_context(
            selected_market=result_data["selected_market"],
            isbn_text=result_data["isbn_text"],
            selected_supplier_names=result_data["selected_supplier_names"],
            results=result_data["results"],
            job=job,
        )
    else:
        context = page_context(
            selected_market=payload["market"],
            isbn_text=payload["isbn_text"],
            selected_supplier_names=payload["supplier_names"],
            results=None,
            job=job,
        )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context=context,
    )


# ---------------------------------------------------------
# Live status API
# ---------------------------------------------------------

@app.get("/api/search/{job_id}")
def search_status(job_id: str):
    job = SEARCH_QUEUE.get(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Search job not found",
        )

    data = job.public_status()
    data["queue_position"] = SEARCH_QUEUE.queue_position(job_id)

    return JSONResponse(content=data)
