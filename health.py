"""
health.py — per-provider health tracking backing `GET /health`
(provider-catalog spec, task 8.2). Purely observational: `cache.run_lookup`
calls `record_request`/`record_success`/`record_failure` but never reads
this data back to make a routing decision — "no fallback or fan-out" and
"health must not influence provider choice" both hold regardless of what
this module records.
"""

from __future__ import annotations

import datetime

from sqlalchemy import text

from db.models import ProviderHealth


def record_request(db, kind: str, provider: str) -> None:
    row = db.query(ProviderHealth).filter_by(kind=kind, provider=provider).first()
    if row is None:
        row = ProviderHealth(kind=kind, provider=provider, requests_count=0, success_count=0, failure_count=0)
        db.add(row)
        db.flush()
    row.requests_count += 1
    db.commit()


def record_success(db, kind: str, provider: str) -> None:
    row = db.query(ProviderHealth).filter_by(kind=kind, provider=provider).first()
    if row is not None:
        row.success_count += 1
        row.last_success_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()


def record_failure(db, kind: str, provider: str, message: str) -> None:
    row = db.query(ProviderHealth).filter_by(kind=kind, provider=provider).first()
    if row is not None:
        row.failure_count += 1
        row.last_failure_at = datetime.datetime.now(datetime.timezone.utc)
        row.last_failure_message = message
        db.commit()


def get_all(db) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT kind, provider, requests_count, success_count, failure_count,
                   last_success_at, last_failure_at, last_failure_message
            FROM provider_health
            ORDER BY kind, provider
            """
        )
    ).all()
    return [
        {
            "kind": kind,
            "provider": provider,
            "requestsCount": requests_count,
            "successCount": success_count,
            "failureCount": failure_count,
            "hitCount": max(requests_count - success_count - failure_count, 0),
            "lastSuccessAt": last_success_at.isoformat() if last_success_at else None,
            "lastFailureAt": last_failure_at.isoformat() if last_failure_at else None,
            "lastFailureMessage": last_failure_message,
        }
        for (
            kind, provider, requests_count, success_count, failure_count,
            last_success_at, last_failure_at, last_failure_message,
        ) in rows
    ]
