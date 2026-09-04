"""Deterministic PostgreSQL evidence lookup for catalogued BI metrics."""

from __future__ import annotations

import re
from dataclasses import dataclass

import psycopg2
from psycopg2.extras import RealDictCursor

from backend.core.settings import PGVECTOR_URL
from backend.domains.bi.application.rag_errors import RagPipelineContractError
from backend.domains.bi.domain.catalog import METRIC_CATALOG, SourceMetricDefinition
from backend.domains.bi.domain.extraction_models import (
    BiContextCell,
    BiMetricExtractionRequest,
)
from backend.platform.postgres.pool import get_pooled_raw_connection

_PERIOD_DATE = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")
_ROW_HEADER = re.compile(
    r"(?:^|\|)\s*Row Header:\s*(.*?)\s*\|\s*Column Header:",
    re.IGNORECASE,
)
_NORMALIZED_TEXT = re.compile(r"[^0-9a-z\uac00-\ud7a3]+")
_MISSING_VALUES = ("", "-", "?", "NA", "N/A", "NM", "#PEND", "NULL")


def _normalize(value: str) -> str:
    return _NORMALIZED_TEXT.sub("", value.casefold())


def _unique_normalized(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(normalized for value in values if (normalized := _normalize(value))))


def _ordered_metric_aliases(definition: SourceMetricDefinition) -> tuple[str, ...]:
    """Return aliases in business priority order, not just match order.

    The catalog's canonical English label must win over broader aliases.  This
    matters for workbooks that expose genuinely different rows such as
    ``Total Revenue``, ``Revenue`` and ``As-Reported Total Revenue``.
    """

    return _unique_normalized(
        (
            definition.label_en,
            *definition.row_header_hints,
            *definition.aliases_en,
            definition.label_ko,
            *definition.aliases_ko,
        )
    )


def _source_row_header(source_text: str) -> str:
    match = _ROW_HEADER.search(source_text)
    if match is None:
        return ""
    # Serialized hierarchy uses ``>``.  Rank the leaf metric, not its parents.
    return match.group(1).rsplit(">", maxsplit=1)[-1].strip()


def _metric_cell_rank(cell: BiContextCell, aliases: tuple[str, ...]) -> int:
    row_header = _normalize(_source_row_header(cell.source_text))
    if not row_header:
        return len(aliases) * 2 + 1
    try:
        return aliases.index(row_header)
    except ValueError:
        pass

    # Suffix matching supports prefixed vendor labels, but remains lower
    # priority than every exact catalog alias (e.g. As-Reported Total Revenue).
    suffix_positions = tuple(
        index
        for index, alias in enumerate(aliases)
        if len(alias) >= 10 and row_header.endswith(alias)
    )
    if suffix_positions:
        return len(aliases) + min(suffix_positions)
    return len(aliases) * 2 + 1


def _prioritize_metric_cells(
    cells: tuple[BiContextCell, ...],
    definition: SourceMetricDefinition,
    *,
    limit: int,
) -> tuple[BiContextCell, ...]:
    """Keep every candidate at the best available alias priority.

    Keeping all best-priority cells preserves ambiguity detection when two
    canonical sources disagree, while preventing lower-priority aliases from
    creating a false conflict.
    """

    if not cells:
        return ()
    aliases = _ordered_metric_aliases(definition)
    ranked = tuple((_metric_cell_rank(cell, aliases), cell) for cell in cells)
    best_rank = min(rank for rank, _cell in ranked)
    return tuple(cell for rank, cell in ranked if rank == best_rank)[:limit]


def _period_terms(request: BiMetricExtractionRequest) -> tuple[tuple[str, ...], str]:
    identity = f"{request.period_id} {request.period_label}"
    date_match = _PERIOD_DATE.search(identity)
    values = [str(request.period_id), request.period_label]
    if date_match:
        year, month, day = date_match.groups()
        values.extend((year, f"FY{year}", f"{year}-{month}-{day}"))
    kind = "ltm" if str(request.period_id).casefold().startswith("ltm-") else "fy"
    return _unique_normalized(tuple(values)), kind


@dataclass(frozen=True, slots=True)
class PostgresBiMetricEvidenceRetriever:
    """Find same-row/same-period evidence before falling back to semantic RAG."""

    database_url: str = PGVECTOR_URL

    def retrieve_metric_cells(
        self,
        request: BiMetricExtractionRequest,
        *,
        limit: int,
    ) -> tuple[BiContextCell, ...]:
        definition = METRIC_CATALOG.get(request.metric_id)
        if not isinstance(definition, SourceMetricDefinition):
            return ()

        aliases = _ordered_metric_aliases(definition)
        suffix_aliases = tuple(alias for alias in aliases if len(alias) >= 10)
        excluded = _unique_normalized(definition.excluded_aliases)
        statement_hints = _unique_normalized(definition.statement_hints)
        period_terms, period_kind = _period_terms(request)
        if not aliases or not period_terms:
            return ()

        try:
            with get_pooled_raw_connection(self.database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SET LOCAL statement_timeout = '20s'")
                    cursor.execute(
                        _METRIC_EVIDENCE_SQL,
                        {
                            "index_id": str(request.source.index_id),
                            "workbook_hash": request.source.workbook_hash,
                            "file_name": request.source.file_name,
                            "aliases": list(aliases),
                            "suffix_aliases": list(suffix_aliases),
                            "excluded": list(excluded),
                            "period_terms": list(period_terms),
                            "period_kind": period_kind,
                            "statement_hints": list(statement_hints),
                            "missing_values": list(_MISSING_VALUES),
                            # Fetch enough alternatives to apply catalog alias
                            # priority after SQL matching.  The public context
                            # limit is still enforced below.
                            "limit": max(32, min(limit * 8, 100)),
                        },
                    )
                    rows = cursor.fetchall()
        except psycopg2.Error as error:
            raise RagPipelineContractError(code="metric_evidence_query_failed") from error
        cells = tuple(BiContextCell.model_validate(dict(row)) for row in rows)
        return _prioritize_metric_cells(cells, definition, limit=limit)


_JSON_ARRAY = """
CASE
    WHEN jsonb_typeof({field}) = 'array' THEN {field}
    WHEN jsonb_typeof({field}) = 'string' THEN jsonb_build_array({field})
    ELSE '[]'::jsonb
END
"""
_ROW_ARRAY = _JSON_ARRAY.format(field="e.cmetadata->'row_header'")
_COLUMN_ARRAY = _JSON_ARRAY.format(field="e.cmetadata->'column_header'")
_NORMALIZE_TOKEN = "regexp_replace(lower(token), '[^0-9a-z\uac00-\ud7a3]+', '', 'g')"
_NORMALIZE_SHEET = (
    "regexp_replace(lower(e.cmetadata->>'sheet_name'), "
    "'[^0-9a-z\uac00-\ud7a3]+', '', 'g')"
)

_METRIC_EVIDENCE_SQL = rf"""
WITH scoped AS (
    SELECT
        e.id,
        e.document,
        e.cmetadata,
        e.cmetadata->>'cell_id' AS cell_id,
        e.cmetadata->>'sheet_name' AS sheet_name,
        e.cmetadata->>'cell_coord' AS cell_coord,
        COALESCE(
            CASE WHEN e.cmetadata->>'row_index' ~ '^\d+$'
                THEN (e.cmetadata->>'row_index')::int END,
            NULLIF(regexp_replace(e.cmetadata->>'cell_coord', '[^0-9]', '', 'g'), '')::int
        ) AS row_index,
        COALESCE(
            CASE WHEN e.cmetadata->>'col_index' ~ '^\d+$'
                THEN (e.cmetadata->>'col_index')::int END,
            0
        ) AS col_index,
        EXISTS (
            SELECT 1 FROM jsonb_array_elements_text({_ROW_ARRAY}) AS row_token(token)
            WHERE {_NORMALIZE_TOKEN} = ANY(%(aliases)s)
        ) AS exact_metric_match,
        (
            SELECT MIN(array_position(%(aliases)s::text[], {_NORMALIZE_TOKEN}))
            FROM jsonb_array_elements_text({_ROW_ARRAY}) AS row_token(token)
            WHERE {_NORMALIZE_TOKEN} = ANY(%(aliases)s)
        ) AS exact_metric_rank,
        EXISTS (
            SELECT 1 FROM jsonb_array_elements_text({_ROW_ARRAY}) AS row_token(token)
            CROSS JOIN unnest(%(suffix_aliases)s::text[]) AS wanted(alias)
            WHERE right({_NORMALIZE_TOKEN}, length(wanted.alias)) = wanted.alias
        ) AS suffix_metric_match,
        (
            SELECT MIN(array_position(%(suffix_aliases)s::text[], wanted.alias))
            FROM jsonb_array_elements_text({_ROW_ARRAY}) AS row_token(token)
            CROSS JOIN unnest(%(suffix_aliases)s::text[]) AS wanted(alias)
            WHERE right({_NORMALIZE_TOKEN}, length(wanted.alias)) = wanted.alias
        ) AS suffix_metric_rank,
        EXISTS (
            SELECT 1 FROM jsonb_array_elements_text({_ROW_ARRAY}) AS row_token(token)
            CROSS JOIN unnest(%(excluded)s::text[]) AS blocked(alias)
            WHERE right({_NORMALIZE_TOKEN}, length(blocked.alias)) = blocked.alias
        ) AS excluded_metric_match,
        EXISTS (
            SELECT 1 FROM jsonb_array_elements_text({_COLUMN_ARRAY}) AS column_token(token)
            WHERE {_NORMALIZE_TOKEN} = ANY(%(period_terms)s)
        ) AS period_match,
        EXISTS (
            SELECT 1 FROM jsonb_array_elements_text({_COLUMN_ARRAY}) AS column_token(token)
            WHERE {_NORMALIZE_TOKEN} IN ('ltm', 'lasttwelvemonths', 'trailingtwelvemonths')
        ) AS ltm_match,
        CASE
            WHEN {_NORMALIZE_SHEET} = ANY(%(statement_hints)s)
                THEN array_position(%(statement_hints)s::text[], {_NORMALIZE_SHEET})
            ELSE 999
        END AS statement_rank
    FROM langchain_pg_embedding e
    JOIN langchain_pg_collection c ON c.uuid = e.collection_id
    WHERE c.name = %(index_id)s
      AND e.cmetadata->>'workbook_hash' = %(workbook_hash)s
      AND e.cmetadata->>'file_name' = %(file_name)s
      AND NULLIF(BTRIM(e.cmetadata->>'cell_coord'), '') IS NOT NULL
), coordinate_matches AS (
    SELECT
        sheet_name,
        cell_coord,
        MAX(row_index) AS row_index,
        MAX(col_index) AS col_index,
        BOOL_OR(exact_metric_match) AS exact_metric_match,
        MIN(exact_metric_rank) AS exact_metric_rank,
        BOOL_OR(suffix_metric_match) AS suffix_metric_match,
        MIN(suffix_metric_rank) AS suffix_metric_rank,
        BOOL_OR(excluded_metric_match) AS excluded_metric_match,
        BOOL_OR(period_match) AS period_match,
        BOOL_OR(ltm_match) AS ltm_match,
        MIN(statement_rank) AS statement_rank
    FROM scoped
    GROUP BY sheet_name, cell_coord
), period_candidates AS (
    SELECT
        matches.*,
        BOOL_OR(matches.ltm_match) OVER (
            PARTITION BY matches.sheet_name, matches.row_index
        ) AS row_has_explicit_ltm,
        COUNT(*) OVER (
            PARTITION BY matches.sheet_name, matches.row_index
        ) AS repeated_period_count,
        ROW_NUMBER() OVER (
            PARTITION BY matches.sheet_name, matches.row_index
            ORDER BY matches.col_index, matches.cell_coord
        ) AS period_rank_ascending,
        ROW_NUMBER() OVER (
            PARTITION BY matches.sheet_name, matches.row_index
            ORDER BY matches.col_index DESC, matches.cell_coord DESC
        ) AS period_rank_descending
    FROM coordinate_matches matches
    WHERE (matches.exact_metric_match OR matches.suffix_metric_match)
      AND NOT matches.excluded_metric_match
      AND matches.period_match
), eligible_coordinates AS (
    SELECT *
    FROM period_candidates
    WHERE (
        %(period_kind)s = 'ltm'
        AND (
            ltm_match
            OR (
                NOT row_has_explicit_ltm
                AND repeated_period_count > 1
                AND period_rank_descending = 1
            )
        )
    ) OR (
        %(period_kind)s = 'fy'
        AND NOT ltm_match
        AND (
            row_has_explicit_ltm
            OR repeated_period_count = 1
            OR period_rank_ascending = 1
        )
    )
), ranked AS (
    SELECT
        COALESCE(NULLIF(BTRIM(s.cell_id), ''), s.sheet_name || ' Cell ' || s.cell_coord)
            AS cell_id,
        s.sheet_name,
        UPPER(s.cell_coord) AS cell_coord,
        LEFT(s.document, 2000) AS source_text,
        ROW_NUMBER() OVER (
            PARTITION BY UPPER(s.sheet_name), UPPER(s.cell_coord)
            ORDER BY
                CASE WHEN s.cmetadata->>'variant' = 'header_with_value' THEN 0 ELSE 1 END,
                CASE WHEN s.ltm_match THEN 0 ELSE 1 END,
                CASE WHEN jsonb_typeof(s.cmetadata->'row_header') = 'array'
                    THEN jsonb_array_length(s.cmetadata->'row_header') ELSE 0 END DESC,
                CASE WHEN jsonb_typeof(s.cmetadata->'column_header') = 'array'
                    THEN jsonb_array_length(s.cmetadata->'column_header') ELSE 0 END DESC,
                s.id
        ) AS evidence_rank,
        CASE
            WHEN matches.exact_metric_match THEN matches.exact_metric_rank
            ELSE 1000 + matches.suffix_metric_rank
        END AS metric_rank,
        matches.statement_rank
    FROM scoped s
    JOIN eligible_coordinates matches
      ON matches.sheet_name = s.sheet_name AND matches.cell_coord = s.cell_coord
    WHERE UPPER(BTRIM(COALESCE(s.cmetadata->>'cell_value', ''))) <> ALL(%(missing_values)s)
      AND s.document NOT ILIKE '%%Cell Value: ?%%'
      AND s.document NOT ILIKE '%%Cell Value: NA%%'
)
SELECT cell_id, sheet_name, cell_coord, source_text
FROM ranked
WHERE evidence_rank = 1
ORDER BY metric_rank, statement_rank, UPPER(sheet_name), UPPER(cell_coord)
LIMIT %(limit)s
"""


__all__ = ["PostgresBiMetricEvidenceRetriever"]
