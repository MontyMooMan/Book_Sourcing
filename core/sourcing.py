from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable

from core.models import Offer


@dataclass
class SourcingResult:
    isbn: str
    offers: list[Offer]


ProgressCallback = Callable[[int, int, str, str], None]


class SourcingEngine:
    def __init__(self, suppliers, max_workers: int = 12, progress_callback: ProgressCallback | None = None):
        self.suppliers = suppliers
        self.max_workers = max_workers
        self.progress_callback = progress_callback

    def _report_progress(self, completed: int, total: int, isbn: str, supplier_name: str) -> None:
        if self.progress_callback is None:
            return
        try:
            self.progress_callback(completed, total, isbn, supplier_name)
        except Exception as exc:
            print(f"Progress callback error: {exc}")

    def lookup(self, isbn: str) -> SourcingResult:
        offers = []
        total = len(self.suppliers)
        completed = 0

        with ThreadPoolExecutor(
            max_workers=min(self.max_workers, max(1, len(self.suppliers)))
        ) as executor:
            futures = {
                executor.submit(supplier.lookup, isbn): supplier
                for supplier in self.suppliers
            }

            for future in as_completed(futures):
                supplier = futures[future]
                try:
                    supplier_offers = future.result()
                    if supplier_offers:
                        offers.extend(supplier_offers)
                        for offer in supplier_offers:
                            if offer.price is not None:
                                print(f"{isbn} | {offer.supplier} | {offer.currency} {offer.price}")
                            else:
                                print(f"{isbn} | {offer.supplier} | No price")
                    else:
                        print(f"{isbn} | {supplier.name} | Not found")
                except Exception as exc:
                    print(f"{isbn} | {supplier.name} | ERROR: {exc}")
                finally:
                    completed += 1
                    self._report_progress(completed, total, isbn, supplier.name)

        return SourcingResult(isbn=isbn, offers=offers)

    def lookup_many(self, isbns: list[str]) -> list[SourcingResult]:
        if not isbns:
            return []

        results_by_isbn = {isbn: [] for isbn in isbns}
        total_jobs = len(isbns) * len(self.suppliers)
        completed_jobs = 0
        future_jobs = {}

        try:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                for isbn in isbns:
                    for supplier in self.suppliers:
                        future = executor.submit(supplier.lookup, isbn)
                        future_jobs[future] = (isbn, supplier)

                # Handle results in completion order so progress is genuinely live.
                for future in as_completed(future_jobs):
                    isbn, supplier = future_jobs[future]
                    try:
                        supplier_offers = future.result()
                        if supplier_offers:
                            results_by_isbn[isbn].extend(supplier_offers)
                            for offer in supplier_offers:
                                if offer.price is not None:
                                    print(f"{isbn} | {offer.supplier} | {offer.currency} {offer.price}")
                                else:
                                    print(f"{isbn} | {offer.supplier} | No price")
                        else:
                            print(f"{isbn} | {supplier.name} | Not found")
                    except Exception as exc:
                        print(f"{isbn} | {supplier.name} | ERROR: {exc}")
                    finally:
                        completed_jobs += 1
                        self._report_progress(
                            completed_jobs,
                            total_jobs,
                            isbn,
                            supplier.name,
                        )
        finally:
            self._close_batch_resources()

        return [
            SourcingResult(isbn=isbn, offers=results_by_isbn[isbn])
            for isbn in isbns
        ]

    def _close_batch_resources(self):
        for supplier in self.suppliers:
            shutdown = getattr(supplier, "shutdown_browser", None)
            if not callable(shutdown):
                continue
            try:
                shutdown()
            except Exception as exc:
                print(f"{supplier.name} cleanup error: {exc}")
