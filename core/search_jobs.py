from __future__ import annotations

import json
import logging
import queue
import threading
import uuid

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    insert,
    select,
    update,
)

from core.database import engine
from core.logging_config import configure_logging
from core.models import Offer

configure_logging()
logger = logging.getLogger("booksourcing.jobs")


_JOB_METADATA = MetaData()

_SEARCH_JOBS = Table(
    "search_jobs",
    _JOB_METADATA,
    Column("id", String(32), primary_key=True),
    Column("payload_json", Text, nullable=False),
    Column("status", String(32), nullable=False),
    Column("completed_checks", Integer, nullable=False),
    Column("total_checks", Integer, nullable=False),
    Column("message", Text, nullable=False),
    Column("result_json", Text),
    Column("error", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("started_at", String(64)),
    Column("finished_at", String(64)),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {
            "__type__": "Decimal",
            "value": str(value),
        }

    if isinstance(value, Offer):
        return {
            "__type__": "Offer",
            "value": {
                key: _json_safe(item)
                for key, item in asdict(value).items()
            },
        }

    if is_dataclass(value):
        return {
            "__type__": value.__class__.__name__,
            "value": {
                key: _json_safe(item)
                for key, item in asdict(value).items()
            },
        }

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            _json_safe(item)
            for item in value
        ]

    if value is None or isinstance(
        value,
        (str, int, float, bool),
    ):
        return value

    return str(value)


def _json_restore(value: Any) -> Any:
    if isinstance(value, list):
        return [
            _json_restore(item)
            for item in value
        ]

    if not isinstance(value, dict):
        return value

    value_type = value.get("__type__")

    if value_type == "Decimal":
        return Decimal(
            value.get("value", "0")
        )

    if value_type == "Offer":
        raw = value.get("value", {})
        restored = {
            key: _json_restore(item)
            for key, item in raw.items()
        }
        return Offer(**restored)

    return {
        key: _json_restore(item)
        for key, item in value.items()
    }


@dataclass
class SearchJob:
    id: str
    payload: dict[str, Any]
    status: str = "queued"
    completed_checks: int = 0
    total_checks: int = 0
    message: str = "Waiting to start"
    result: Any = None
    error: str = ""
    created_at: str = field(
        default_factory=_now_iso
    )
    started_at: str | None = None
    finished_at: str | None = None

    _persist_callback: Callable[
        ["SearchJob"],
        None,
    ] | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def persist(self) -> None:
        if self._persist_callback is not None:
            self._persist_callback(self)

    def set_progress(
        self,
        completed: int,
        total: int,
        message: str = "",
    ) -> None:
        self.completed_checks = max(
            0,
            completed,
        )
        self.total_checks = max(
            0,
            total,
        )

        if message:
            self.message = message

        self.persist()

    @property
    def progress_percent(self) -> int:
        if self.total_checks <= 0:
            return 0

        return min(
            100,
            round(
                (
                    self.completed_checks
                    / self.total_checks
                )
                * 100
            ),
        )

    def public_status(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "completed_checks": self.completed_checks,
            "total_checks": self.total_checks,
            "progress_percent": self.progress_percent,
            "message": self.message,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class SearchJobStore:
    def __init__(self) -> None:
        _JOB_METADATA.create_all(engine)

    def save(
        self,
        job: SearchJob,
    ) -> None:
        payload_json = json.dumps(
            _json_safe(job.payload),
            ensure_ascii=False,
        )

        result_json = None

        if job.result is not None:
            result_json = json.dumps(
                _json_safe(job.result),
                ensure_ascii=False,
            )

        values = {
            "id": job.id,
            "payload_json": payload_json,
            "status": job.status,
            "completed_checks":
                job.completed_checks,
            "total_checks":
                job.total_checks,
            "message": job.message,
            "result_json": result_json,
            "error": job.error,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
        }

        with engine.begin() as connection:
            existing = connection.execute(
                select(_SEARCH_JOBS.c.id)
                .where(
                    _SEARCH_JOBS.c.id
                    == job.id
                )
            ).first()

            if existing is None:
                connection.execute(
                    insert(_SEARCH_JOBS)
                    .values(**values)
                )
            else:
                connection.execute(
                    update(_SEARCH_JOBS)
                    .where(
                        _SEARCH_JOBS.c.id
                        == job.id
                    )
                    .values(**values)
                )

    def get(
        self,
        job_id: str,
    ) -> SearchJob | None:
        with engine.connect() as connection:
            row = connection.execute(
                select(_SEARCH_JOBS)
                .where(
                    _SEARCH_JOBS.c.id
                    == job_id
                )
            ).mappings().first()

        if row is None:
            return None

        payload = _json_restore(
            json.loads(
                row["payload_json"]
            )
        )

        result = None

        if row["result_json"]:
            result = _json_restore(
                json.loads(
                    row["result_json"]
                )
            )

        return SearchJob(
            id=row["id"],
            payload=payload,
            status=row["status"],
            completed_checks=(
                row["completed_checks"]
                or 0
            ),
            total_checks=(
                row["total_checks"]
                or 0
            ),
            message=(
                row["message"]
                or ""
            ),
            result=result,
            error=row["error"] or "",
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )

    def unfinished_jobs(
        self,
    ) -> list[SearchJob]:
        with engine.connect() as connection:
            rows = connection.execute(
                select(_SEARCH_JOBS)
                .where(
                    _SEARCH_JOBS.c.status.in_(
                        ["queued", "running"]
                    )
                )
                .order_by(
                    _SEARCH_JOBS.c.created_at
                )
            ).mappings().all()

        jobs = []

        for row in rows:
            payload = _json_restore(
                json.loads(
                    row["payload_json"]
                )
            )

            jobs.append(
                SearchJob(
                    id=row["id"],
                    payload=payload,
                    status="queued",
                    completed_checks=0,
                    total_checks=(
                        row["total_checks"]
                        or 0
                    ),
                    message=(
                        "Recovered after restart"
                    ),
                    result=None,
                    error="",
                    created_at=row["created_at"],
                    started_at=None,
                    finished_at=None,
                )
            )

        return jobs

    def queued_job_ids(
        self,
    ) -> list[str]:
        with engine.connect() as connection:
            rows = connection.execute(
                select(
                    _SEARCH_JOBS.c.id
                )
                .where(
                    _SEARCH_JOBS.c.status
                    == "queued"
                )
                .order_by(
                    _SEARCH_JOBS.c.created_at
                )
            ).all()

        return [
            row[0]
            for row in rows
        ]


    def requeue_running_jobs(
        self,
    ) -> int:
        with engine.begin() as connection:
            result = connection.execute(
                update(_SEARCH_JOBS)
                .where(
                    _SEARCH_JOBS.c.status
                    == "running"
                )
                .values(
                    status="queued",
                    completed_checks=0,
                    message="Recovered after worker restart",
                    error="",
                    started_at=None,
                    finished_at=None,
                )
            )

        count = result.rowcount or 0

        if count:
            logger.warning(
                "Recovered %s interrupted search job(s).",
                count,
            )

        return count

    def claim_next_job(
        self,
    ) -> SearchJob | None:
        with engine.begin() as connection:
            row = connection.execute(
                select(_SEARCH_JOBS)
                .where(
                    _SEARCH_JOBS.c.status
                    == "queued"
                )
                .order_by(
                    _SEARCH_JOBS.c.created_at
                )
                .with_for_update(
                    skip_locked=True
                )
                .limit(1)
            ).mappings().first()

            if row is None:
                return None

            started_at = _now_iso()

            connection.execute(
                update(_SEARCH_JOBS)
                .where(
                    _SEARCH_JOBS.c.id
                    == row["id"]
                )
                .values(
                    status="running",
                    completed_checks=0,
                    message="Search starting",
                    error="",
                    started_at=started_at,
                    finished_at=None,
                )
            )

        payload = _json_restore(
            json.loads(
                row["payload_json"]
            )
        )

        return SearchJob(
            id=row["id"],
            payload=payload,
            status="running",
            completed_checks=0,
            total_checks=(
                row["total_checks"]
                or 0
            ),
            message="Search starting",
            result=None,
            error="",
            created_at=row["created_at"],
            started_at=started_at,
            finished_at=None,
        )


class SearchQueue:
    """
    PostgreSQL-backed FIFO queue.

    The web process submits and reads jobs only.
    A separate worker process claims and executes queued jobs.
    """

    def __init__(
        self,
        handler: Callable[
            [SearchJob],
            Any,
        ],
        *,
        worker_mode: bool = False,
        poll_seconds: float = 1.0,
    ):
        self.handler = handler
        self.worker_mode = worker_mode
        self.poll_seconds = poll_seconds
        self._store = SearchJobStore()
        self._stop_requested = threading.Event()

        if self.worker_mode:
            self._store.requeue_running_jobs()

    def _attach_persistence(
        self,
        job: SearchJob,
    ) -> SearchJob:
        job._persist_callback = (
            self._store.save
        )
        return job

    def submit(
        self,
        payload: dict[str, Any],
    ) -> SearchJob:
        job = SearchJob(
            id=uuid.uuid4().hex[:12],
            payload=payload,
        )

        self._attach_persistence(job)
        job.persist()

        return job

    def get(
        self,
        job_id: str,
    ) -> SearchJob | None:
        job = self._store.get(
            job_id
        )

        if job is None:
            return None

        return self._attach_persistence(
            job
        )

    def queue_position(
        self,
        job_id: str,
    ) -> int | None:
        job = self.get(
            job_id
        )

        if (
            job is None
            or job.status != "queued"
        ):
            return None

        queued_ids = (
            self._store
            .queued_job_ids()
        )

        try:
            return (
                queued_ids.index(
                    job_id
                )
                + 1
            )
        except ValueError:
            return None

    def run_worker_forever(
        self,
    ) -> None:
        if not self.worker_mode:
            raise RuntimeError(
                "SearchQueue is not in worker mode."
            )

        logger.info(
            "Search worker started; waiting for queued jobs."
        )

        while not self._stop_requested.is_set():
            job = self._store.claim_next_job()

            if job is None:
                self._stop_requested.wait(
                    self.poll_seconds
                )
                continue

            self._attach_persistence(job)

            logger.info(
                "Claimed search job %s",
                job.id,
            )

            try:
                job.result = self.handler(job)

                job.status = "complete"
                job.completed_checks = (
                    job.total_checks
                )
                job.message = (
                    "Search complete"
                )

            except Exception as exc:
                job.status = "failed"
                job.error = str(exc)
                job.message = "Search failed"

                logger.exception(
                    "Search job %s failed: %s",
                    job.id,
                    exc,
                )

            finally:
                job.finished_at = _now_iso()
                job.persist()

                logger.info(
                    "Finished search job %s with status %s",
                    job.id,
                    job.status,
                )

        logger.info("Search worker stopped.")

    def stop_worker(
        self,
    ) -> None:
        self._stop_requested.set()

