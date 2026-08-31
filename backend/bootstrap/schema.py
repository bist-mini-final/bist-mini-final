"""Development schema initialization composed from domain-owned fragments."""

from __future__ import annotations

import logging

from backend.domains.benchmark.infrastructure.postgres import BENCHMARK_SCHEMA_SQL
from backend.domains.bi.infrastructure.postgres import BI_SCHEMA_SQL
from backend.domains.chatbot.infrastructure.postgres.schema import CHATBOT_SCHEMA_SQL
from backend.domains.data_sources.infrastructure.postgres.schema import DATA_SOURCE_SCHEMA_SQL
from backend.domains.workflow.infrastructure.postgres.schema import WORKFLOW_SCHEMA_SQL
from backend.platform.postgres.pool import get_pooled_raw_connection

logger = logging.getLogger(__name__)


def ensure_application_schema(database_url: str) -> bool:
    """Initialize local/development schema without hiding domain ownership."""

    connection = None
    try:
        connection = get_pooled_raw_connection(database_url)
        with connection.cursor() as cursor:
            for schema_sql in (
                DATA_SOURCE_SCHEMA_SQL,
                WORKFLOW_SCHEMA_SQL,
                CHATBOT_SCHEMA_SQL,
                BI_SCHEMA_SQL,
                BENCHMARK_SCHEMA_SQL,
            ):
                cursor.execute(schema_sql)
        connection.commit()
        return True
    except Exception as error:
        logger.warning("PostgreSQL 스키마 초기화에 실패했습니다: %s", error, exc_info=True)
        return False
    finally:
        if connection is not None:
            connection.close()


__all__ = ["ensure_application_schema"]
