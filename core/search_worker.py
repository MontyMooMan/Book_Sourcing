from __future__ import annotations

import logging
import signal

from core.logging_config import configure_logging
from core.search_jobs import SearchQueue
from web.app import run_search_job


def main() -> None:
    configure_logging()
    logger = logging.getLogger(
        "booksourcing.worker"
    )
    logger.info("Starting search worker process")

    worker = SearchQueue(
        handler=run_search_job,
        worker_mode=True,
        poll_seconds=1.0,
    )

    def request_stop(*_args) -> None:
        worker.stop_worker()

    signal.signal(
        signal.SIGINT,
        request_stop,
    )
    signal.signal(
        signal.SIGTERM,
        request_stop,
    )

    worker.run_worker_forever()


if __name__ == "__main__":
    main()
