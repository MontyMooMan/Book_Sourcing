from __future__ import annotations

import logging
import sys

from core.config import settings


_CONFIGURED = False


def configure_logging() -> None:
    global _CONFIGURED

    if _CONFIGURED:
        return

    level = getattr(
        logging,
        settings.log_level,
        logging.INFO,
    )

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers when modules are imported more than once.
    if not root.handlers:
        handler = logging.StreamHandler(
            sys.stdout
        )

        formatter = logging.Formatter(
            fmt=(
                "%(asctime)s | %(levelname)s | "
                "%(name)s | %(message)s"
            ),
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        handler.setFormatter(formatter)
        root.addHandler(handler)

    _CONFIGURED = True
