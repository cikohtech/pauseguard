"""Data layer: repositories behind two interfaces (base.py), picked by settings.

    get_transaction_repo()  DATA_BACKEND=sqlite | bigquery   bank data (read-only)
    get_analytics_repo()    DATA_BACKEND=sqlite | bigquery   checks_analytics (append-only)
    get_state_repo()        STATE_BACKEND=firestore | memory  app state

Backends are imported lazily, so a unit test never loads a cloud client it does not use.
"""

from __future__ import annotations

from app.config import Settings, get_settings
from app.data.base import AnalyticsRepo, StateRepo, TransactionRepo


def get_transaction_repo(settings: Settings | None = None) -> TransactionRepo:
    settings = settings or get_settings()
    if settings.data_backend == "bigquery":
        from app.data.bigquery_repo import BigQueryTransactionRepo

        return BigQueryTransactionRepo(
            project=settings.google_cloud_project,
            dataset=settings.bq_dataset,
            location=settings.data_region,
        )
    from app.data.sqlite_repo import SqliteTransactionRepo

    return SqliteTransactionRepo(settings.sqlite_path)


def get_analytics_repo(settings: Settings | None = None) -> AnalyticsRepo:
    settings = settings or get_settings()
    if settings.data_backend == "bigquery":
        from app.data.bigquery_repo import BigQueryAnalyticsRepo

        return BigQueryAnalyticsRepo(
            project=settings.google_cloud_project,
            dataset=settings.bq_dataset,
            location=settings.data_region,
        )
    from app.data.sqlite_repo import SqliteAnalyticsRepo

    return SqliteAnalyticsRepo(settings.sqlite_path)


def get_state_repo(settings: Settings | None = None) -> StateRepo:
    settings = settings or get_settings()
    if settings.state_backend == "memory":
        from app.data.memory_repo import MemoryStateRepo

        return MemoryStateRepo()
    from app.data.firestore_repo import FirestoreStateRepo

    settings.export_sdk_env()  # FIRESTORE_EMULATOR_HOST must be in os.environ for the client
    return FirestoreStateRepo(project=settings.firestore_project)
