"""Prune legacy title-region embedding variants without re-embedding cells.

The command is intentionally scoped to the four synthetic company Key Stats
collections that predate ``structured-cell-v6-company-scoped``.  It preserves
the collection UUID and every title-free row/column hierarchy projection, so
the existing vectors and collection-local HNSW contract remain valid.

Run without ``--apply`` for a read-only plan.  Applying the plan performs all
deletes and metadata updates in one transaction, then rebuilds the four HNSW
indexes concurrently.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import psycopg
from psycopg import sql

from backend.core.settings import PGVECTOR_URL

COMPACTION_VERSION = "semantic-title-prune-v1"


@dataclass(frozen=True)
class CompactionTarget:
    index_id: str
    file_name: str


TARGETS = (
    CompactionTarget(
        "idx_6f56608f39b90ce741f7589667e81d9bba7999f8a1f140a543c2d3d623d21ba4",
        "SPG_Company_KeyStats_01_amesoft.xlsm",
    ),
    CompactionTarget(
        "27904fbd1eaa13b45618eae270f63d0d3c4a8cb7ee50111dee9eb9cf3b5d512c",
        "SPG_Company_KeyStats_Bistelligence_AI_DX_Growth.xlsm",
    ),
    CompactionTarget(
        "1873056acbca34a7ed67328540923f55a4be017315cfdc133fa753ac2e157348",
        "SPG_Company_KeyStats_Coldplay_AI_DX_Stable.xlsm",
    ),
    CompactionTarget(
        "3f755b47af8e86a98545e45a2ac8be5aeae9d4dc27c108c588f895aa013b7ab4",
        "SPG_Company_KeyStats_DH_Innovation_AI_DX_Decline.xlsm",
    ),
)


POLLUTED_ROW_HEADER_SQL = """
EXISTS (
    SELECT 1
    FROM jsonb_array_elements_text(
        COALESCE(NULLIF(e.cmetadata->>'row_header', ''), '[]')::jsonb
    ) AS header(value)
    WHERE lower(trim(header.value)) ~
          '^(source[[:space:]]*:|data[[:space:]]+in([[:space:]]|\\(|$)|fiscal[[:space:]]+year[[:space:]]+ended|ltm$)'
       OR header.value ~ '[—-][[:space:]]*(Income Statement|Balance Sheet|Cash Flow)$'
       OR lower(trim(header.value)) = lower(trim(c.cmetadata->>'company_name'))
)
"""


def _database_url() -> str:
    return PGVECTOR_URL.replace("postgresql+psycopg://", "postgresql://")


def _target_rows(cursor: Any) -> list[tuple[str, UUID, str, int, int]]:
    cursor.execute(
        f"""
        SELECT c.name,
               c.uuid,
               c.cmetadata->>'file_name' AS file_name,
               COUNT(e.id) AS before_count,
               COUNT(e.id) FILTER (WHERE {POLLUTED_ROW_HEADER_SQL}) AS removable_count
        FROM langchain_pg_collection AS c
        JOIN langchain_pg_embedding AS e ON e.collection_id = c.uuid
        WHERE c.name = ANY(%s)
        GROUP BY c.name, c.uuid, c.cmetadata::text
        ORDER BY file_name;
        """,
        ([target.index_id for target in TARGETS],),
    )
    return [
        (str(row[0]), UUID(str(row[1])), str(row[2]), int(row[3]), int(row[4]))
        for row in cursor.fetchall()
    ]


def _validate_targets(rows: list[tuple[str, UUID, str, int, int]]) -> None:
    expected = {target.index_id: target.file_name for target in TARGETS}
    actual = {row[0]: row[2] for row in rows}
    if actual != expected:
        raise RuntimeError(
            "정리 대상 collection이 예상과 다릅니다: "
            f"expected={expected!r} actual={actual!r}"
        )
    already_compacted = [row for row in rows if row[4] == 0]
    if already_compacted and len(already_compacted) != len(rows):
        raise RuntimeError(
            "일부 collection만 이미 정리되어 있어 자동 적용하지 않습니다"
        )
    for index_id, _uuid, _file_name, before_count, removable_count in rows:
        retained = before_count - removable_count
        if before_count <= 0 or removable_count < 0 or retained < 5_000:
            raise RuntimeError(
                f"비정상 정리 계획입니다: {index_id} "
                f"before={before_count} removable={removable_count} retained={retained}"
            )


def _print_plan(rows: list[tuple[str, UUID, str, int, int]]) -> None:
    for index_id, _uuid, file_name, before_count, removable_count in rows:
        print(
            f"{file_name}: before={before_count} "
            f"remove={removable_count} retain={before_count - removable_count} "
            f"index_id={index_id}"
        )


def _apply(cursor: Any, rows: list[tuple[str, UUID, str, int, int]]) -> None:
    target_ids = [row[0] for row in rows]
    cursor.execute("SET LOCAL lock_timeout = '10s';")
    cursor.execute("SET LOCAL statement_timeout = '15min';")
    cursor.execute(
        "SELECT pg_advisory_xact_lock(hashtext(%s));",
        ("compact-legacy-key-stats-chunks",),
    )
    cursor.execute(
        f"""
        DELETE FROM langchain_pg_embedding AS e
        USING langchain_pg_collection AS c
        WHERE e.collection_id = c.uuid
          AND c.name = ANY(%s)
          AND {POLLUTED_ROW_HEADER_SQL};
        """,
        (target_ids,),
    )
    deleted_count = int(cursor.rowcount)
    planned_count = sum(row[4] for row in rows)
    if deleted_count != planned_count:
        raise RuntimeError(
            f"삭제 수가 드라이런 계획과 다릅니다: planned={planned_count} deleted={deleted_count}"
        )

    cursor.execute(
        f"""
        SELECT COUNT(*)
        FROM langchain_pg_embedding AS e
        JOIN langchain_pg_collection AS c ON c.uuid = e.collection_id
        WHERE c.name = ANY(%s)
          AND {POLLUTED_ROW_HEADER_SQL};
        """,
        (target_ids,),
    )
    if int(cursor.fetchone()[0]) != 0:
        raise RuntimeError("제목 메타데이터 청크가 삭제 후에도 남아 있습니다")

    cursor.execute(
        """
        WITH variants AS (
            SELECT c.name,
                   e.cmetadata->>'cell_id' AS cell_id,
                   e.cmetadata->>'row_header' AS row_header,
                   e.cmetadata->>'column_header' AS column_header,
                   BOOL_OR(e.cmetadata->>'variant' = 'header_only') AS has_header_only,
                   BOOL_OR(e.cmetadata->>'variant' = 'header_with_value') AS has_value
            FROM langchain_pg_collection AS c
            JOIN langchain_pg_embedding AS e ON e.collection_id = c.uuid
            WHERE c.name = ANY(%s)
            GROUP BY c.name,
                     e.cmetadata->>'cell_id',
                     e.cmetadata->>'row_header',
                     e.cmetadata->>'column_header'
        )
        SELECT COUNT(*)
        FROM variants
        WHERE NOT has_header_only OR NOT has_value;
        """,
        (target_ids,),
    )
    incomplete_pairs = int(cursor.fetchone()[0])
    if incomplete_pairs != 0:
        raise RuntimeError(
            f"header_only/header_with_value 쌍이 불완전합니다: {incomplete_pairs}"
        )

    compacted_at = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        """
        WITH counts AS (
            SELECT collection_id, COUNT(*) AS document_count
            FROM langchain_pg_embedding
            WHERE collection_id = ANY(%s::uuid[])
            GROUP BY collection_id
        )
        UPDATE langchain_pg_collection AS c
        SET cmetadata = (c.cmetadata::jsonb || jsonb_build_object(
            'document_count', counts.document_count,
            'compacted_at', %s::text,
            'compaction_version', %s::text,
            'reembedding_performed', false
        ))::json
        FROM counts
        WHERE c.uuid = counts.collection_id;
        """,
        ([str(row[1]) for row in rows], compacted_at, COMPACTION_VERSION),
    )


def _hnsw_index_name(collection_uuid: UUID, dimension: int = 3072) -> str:
    return f"idx_lc_hnsw_bq_c_{collection_uuid.hex}_{dimension}"


def compact(*, apply: bool, rebuild_indexes: bool = True) -> int:
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            rows = _target_rows(cursor)
            _validate_targets(rows)
            _print_plan(rows)
            if all(row[4] == 0 for row in rows):
                connection.rollback()
                print("already_compacted=true")
                return 0
            if not apply:
                connection.rollback()
                print("dry_run=true")
                return 0
            _apply(cursor, rows)
        connection.commit()

    if rebuild_indexes:
        with psycopg.connect(_database_url(), autocommit=True) as connection:
            with connection.cursor() as cursor:
                for _index_id, collection_uuid, file_name, _before, _remove in rows:
                    index_name = _hnsw_index_name(collection_uuid)
                    print(f"reindexing={file_name} index={index_name}")
                    cursor.execute(
                        sql.SQL("REINDEX INDEX CONCURRENTLY {};").format(
                            sql.Identifier(index_name)
                        )
                    )
                cursor.execute("ANALYZE langchain_pg_embedding;")

    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cursor:
            final_rows = _target_rows(cursor)
            for index_id, _uuid, file_name, after_count, removable_count in final_rows:
                if removable_count != 0:
                    raise RuntimeError(
                        f"정리 후 제거 대상이 남아 있습니다: {index_id}={removable_count}"
                    )
                print(f"completed={file_name} documents={after_count}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="기존 Key Stats title-region 청크를 재임베딩 없이 정리합니다"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="검증된 정리 계획을 실제 PostgreSQL collection에 적용합니다",
    )
    parser.add_argument(
        "--skip-reindex",
        action="store_true",
        help="삭제 후 collection-local HNSW 인덱스 재생성을 생략합니다",
    )
    args = parser.parse_args()
    return compact(apply=args.apply, rebuild_indexes=not args.skip_reindex)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["COMPACTION_VERSION", "TARGETS", "compact", "main"]
