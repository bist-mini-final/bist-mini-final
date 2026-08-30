from dataclasses import dataclass

import psycopg2
from psycopg2.extras import RealDictCursor

from backend.core.settings import PGVECTOR_URL
from backend.domains.bi.domain.extraction_models import BiContextCell, BiRetrievedContext
from backend.domains.bi.domain.models import BiMaterializationSource
from backend.storage.connection_pool import get_pooled_raw_connection

from .profile_models import BiProfileRetrievalRequest
from .rag_errors import RagPipelineContractError


@dataclass(frozen=True, slots=True)
class PostgresBiProfileSheetCatalog:
    database_url: str = PGVECTOR_URL
    limit: int = 64

    def list_sheets(
        self,
        source: BiMaterializationSource,
    ) -> tuple[str, ...]:
        try:
            with get_pooled_raw_connection(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT DISTINCT e.cmetadata->>'sheet_name' AS sheet_name "
                        "FROM langchain_pg_embedding e "
                        "JOIN langchain_pg_collection c ON c.uuid = e.collection_id "
                        "WHERE c.name = %s "
                        "AND e.cmetadata->>'workbook_hash' = %s "
                        "AND e.cmetadata->>'file_name' = %s "
                        "AND NULLIF(BTRIM(e.cmetadata->>'sheet_name'), '') IS NOT NULL "
                        "ORDER BY sheet_name LIMIT %s",
                        (
                            str(source.index_id),
                            source.workbook_hash,
                            source.file_name,
                            self.limit,
                        ),
                    )
                    rows = cursor.fetchall()
        except psycopg2.Error as error:
            raise RagPipelineContractError(code="profile_sheet_query_failed") from error
        return tuple(row[0] for row in rows)


@dataclass(frozen=True, slots=True)
class PostgresBiProfileEvidenceRetriever:
    database_url: str = PGVECTOR_URL
    cells_per_sheet: int = 100

    def retrieve(
        self,
        request: BiProfileRetrievalRequest,
    ) -> BiRetrievedContext:
        if request.sheet_name is None:
            raise RagPipelineContractError(code="profile_sheet_missing")
        try:
            with get_pooled_raw_connection(self.database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SET LOCAL statement_timeout = '20s'")
                    cursor.execute(
                        "WITH candidates AS ("
                        "SELECT e.cmetadata->>'cell_id' AS cell_id, "
                        "e.cmetadata->>'sheet_name' AS sheet_name, "
                        "e.cmetadata->>'cell_coord' AS cell_coord, "
                        "LEFT(e.document, 2000) AS source_text, "
                        "COALESCE(NULLIF(BTRIM(e.cmetadata->>'column_header'), ''), "
                        "CASE WHEN e.cmetadata->>'variant' = 'header_with_value' "
                        "THEN NULLIF(BTRIM(e.cmetadata->>'cell_value'), '') END) "
                        "AS period_header, "
                        "ROW_NUMBER() OVER (PARTITION BY "
                        "COALESCE(NULLIF(BTRIM(e.cmetadata->>'column_header'), ''), "
                        "CASE WHEN e.cmetadata->>'variant' = 'header_with_value' "
                        "THEN NULLIF(BTRIM(e.cmetadata->>'cell_value'), '') END) "
                        "ORDER BY CASE WHEN e.cmetadata->>'variant' = 'header_with_value' "
                        "THEN 0 ELSE 1 END, e.cmetadata->>'cell_coord') AS evidence_rank "
                        "FROM langchain_pg_embedding e "
                        "JOIN langchain_pg_collection c ON c.uuid = e.collection_id "
                        "WHERE c.name = %s "
                        "AND e.cmetadata->>'workbook_hash' = %s "
                        "AND e.cmetadata->>'file_name' = %s "
                        "AND e.cmetadata->>'sheet_name' = %s "
                        "AND COALESCE(NULLIF(BTRIM(e.cmetadata->>'column_header'), ''), "
                        "CASE WHEN e.cmetadata->>'variant' = 'header_with_value' "
                        "THEN NULLIF(BTRIM(e.cmetadata->>'cell_value'), '') END) "
                        "IS NOT NULL"
                        ") SELECT cell_id, sheet_name, cell_coord, source_text "
                        "FROM candidates WHERE evidence_rank = 1 "
                        "ORDER BY period_header LIMIT %s",
                        (
                            str(request.source.index_id),
                            request.source.workbook_hash,
                            request.source.file_name,
                            request.sheet_name,
                            self.cells_per_sheet,
                        ),
                    )
                    rows = cursor.fetchall()
        except psycopg2.Error as error:
            raise RagPipelineContractError(code="profile_evidence_query_failed") from error
        if not rows:
            raise RagPipelineContractError(code="context_cells_missing")
        cells = tuple(BiContextCell.model_validate(row) for row in rows)
        return BiRetrievedContext(
            request_id=request.request_id,
            file_name=request.source.file_name,
            workbook_hash=request.source.workbook_hash,
            index_id=request.source.index_id,
            context_blocks=tuple(
                f"Cell ID: {cell.cell_id} | Sheet: {cell.sheet_name} | "
                f"Coordinate: {cell.cell_coord}\n{cell.source_text}"
                for cell in cells
            ),
            cells=cells,
        )
