"""PostgreSQL full-text, vector, and source-cell retrieval capability."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from langchain_core.documents import Document

from backend.core.settings import PGVECTOR_URL
from backend.domains.data_sources.infrastructure.spreadsheets.langchain_document import (
    langchain_document_to_cell_item,
)
from backend.platform.pgvector.errors import PgVectorStoreError
from backend.platform.postgres.pool import get_pooled_async_connection
from backend.shared.application.embeddings import EmbeddingEncoder
from modules.common.config import DEFAULT_EMBEDDING_MODEL

from .capabilities import PgVectorConnectionCapability

logger = logging.getLogger(__name__)


def _escape_like_term(text: str) -> str:
    """Escape user-derived wildcard characters for a literal ILIKE substring."""
    return text.replace("!", "!!").replace("%", "!%").replace("_", "!_")


class PgVectorRetrievalMixin(PgVectorConnectionCapability):
    """Read-side capability for text, vector, and source-cell retrieval."""

    @staticmethod
    def _keyword_search_query(
        *,
        collection_names: Sequence[str],
        query_text: str,
        k: int,
        company_name: Optional[str],
        sheet_name: Optional[str],
        scoped: bool,
    ) -> tuple[str, List[Any]]:
        where_extra: List[str] = []
        where_params: List[Any] = []
        if scoped and company_name:
            company = company_name.strip()
            where_extra.append(
                "AND (embedding.cmetadata->>'company_name' ILIKE %s ESCAPE '!' "
                "OR embedding.cmetadata->>'company_name' = %s)"
            )
            where_params.extend([f"%{_escape_like_term(company)}%", company])
        if scoped and sheet_name:
            where_extra.append("AND embedding.cmetadata->>'sheet_name' = %s")
            where_params.append(sheet_name)
        extra_sql = " ".join(where_extra)
        return (
            f"""
            SELECT
                embedding.document,
                embedding.cmetadata,
                ts_rank_cd(
                    to_tsvector('simple', embedding.document),
                    plainto_tsquery('simple', %s)
                ) AS fts_score,
                collection.name
            FROM langchain_pg_embedding AS embedding
            JOIN langchain_pg_collection AS collection
              ON collection.uuid = embedding.collection_id
            WHERE collection.name = ANY(%s)
              AND to_tsvector('simple', embedding.document)
                  @@ plainto_tsquery('simple', %s)
              {extra_sql}
            ORDER BY fts_score DESC, embedding.id
            LIMIT %s;
            """,
            [query_text, list(collection_names), query_text, *where_params, k],
        )

    @staticmethod
    def _keyword_search_rows(
        rows: Sequence[Sequence[Any]],
    ) -> List[Tuple[str, Dict[str, Any], float, str]]:
        return [
            (
                str(document),
                metadata if isinstance(metadata, dict) else {},
                float(score) if score is not None else 0.0,
                str(index_id),
            )
            for document, metadata, score, index_id in rows
        ]

    def keyword_search(
        self,
        *,
        collection_names: Sequence[str],
        query_text: str,
        k: int,
        company_name: Optional[str] = None,
        sheet_name: Optional[str] = None,
    ) -> List[Tuple[str, Dict[str, Any], float, str]]:
        """Run one collection-scoped PostgreSQL full-text search."""
        if not collection_names or not query_text.strip() or k <= 0:
            return []

        def fetch(*, scoped: bool) -> List[Tuple[str, Dict[str, Any], float, str]]:
            query, params = self._keyword_search_query(
                collection_names=collection_names,
                query_text=query_text,
                k=k,
                company_name=company_name,
                sheet_name=sheet_name,
                scoped=scoped,
            )
            connection = self._read_connection()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(query, params)
                    rows = cursor.fetchall()
            finally:
                connection.close()
            return self._keyword_search_rows(rows)

        rows = fetch(scoped=True)
        if rows or not (company_name or sheet_name):
            return rows
        return fetch(scoped=False)

    async def keyword_search_async(
        self,
        *,
        collection_names: Sequence[str],
        query_text: str,
        k: int,
        company_name: Optional[str] = None,
        sheet_name: Optional[str] = None,
    ) -> List[Tuple[str, Dict[str, Any], float, str]]:
        """Run collection-scoped FTS through the process async connection pool."""
        if not collection_names or not query_text.strip() or k <= 0:
            return []

        async def fetch(*, scoped: bool) -> List[Tuple[str, Dict[str, Any], float, str]]:
            query, params = self._keyword_search_query(
                collection_names=collection_names,
                query_text=query_text,
                k=k,
                company_name=company_name,
                sheet_name=sheet_name,
                scoped=scoped,
            )
            raw_url = getattr(self, "database_url", PGVECTOR_URL).replace(
                "postgresql+psycopg://",
                "postgresql://",
            )
            async with get_pooled_async_connection(raw_url) as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(query, params)  # type: ignore[arg-type]
                    rows = await cursor.fetchall()
            return self._keyword_search_rows(rows)

        rows = await fetch(scoped=True)
        if rows or not (company_name or sheet_name):
            return rows
        return await fetch(scoped=False)

    def search(
        self,
        index_id: str,
        query_text: str,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        embedding_encoder: Optional[EmbeddingEncoder] = None,
        limit: int = 5,
    ) -> List[Tuple[float, Dict[str, Any]]]:
        """Perform similarity search with quantized HNSW candidates and exact reranking."""
        try:
            if embedding_encoder is None:
                raise PgVectorStoreError("유사도 검색에는 embedding_encoder 주입이 필요합니다")
            vectors = embedding_encoder.encode_for_model([query_text], model_name)
            if not vectors:
                raise PgVectorStoreError("검색 질의 임베딩 결과가 비어 있습니다")
            query_vector = vectors[0]
            hits = self.similarity_search_by_vector_with_score(
                collection_name=index_id,
                embedding=query_vector,
                k=limit,
            )
            results = []
            for doc, score in hits:
                similarity = max(0.0, 1.0 - float(score))
                cell_item = langchain_document_to_cell_item(doc, score=similarity)
                results.append((similarity, cell_item))
            return results
        except Exception as search_err:
            raise PgVectorStoreError(
                f"PostgreSQL pgvector 유사도 검색 실패 ({index_id}): {search_err}"
            ) from search_err

    def similarity_search_by_vector_with_score(
        self,
        collection_name: str,
        embedding: List[float],
        k: int = 10,
        sheet_names: Optional[List[str]] = None,
        company_name: Optional[str] = None,
    ) -> List[Tuple[Any, float]]:
        """
        Search a collection for documents nearest to an embedding vector with optional company and sheet filters.

        Parameters:
            collection_name (str): Name of the collection to search.
            embedding (List[float]): Query embedding vector.
            k (int): Maximum number of results to return.
            sheet_names (Optional[List[str]]): Specific worksheet names to restrict search scope.
            company_name (Optional[str]): Company/Entity identifier to restrict search scope.

        Returns:
            List[Tuple[Any, float]]: Document and cosine-distance pairs, or an empty list when the collection does not exist.

        Raises:
            PgVectorStoreError: If the direct indexed search fails.
        """
        conn = None
        try:
            collection_uuid = self._collection_uuid(collection_name)
            if collection_uuid is None:
                return []
            query_sql, full_params = self._dense_search_query(
                collection_uuid=collection_uuid,
                embedding=embedding,
                k=k,
                sheet_names=sheet_names,
                company_name=company_name,
            )
            conn = self._read_connection()
            with conn.cursor() as cur:
                cur.execute(query_sql, full_params)
                rows = cur.fetchall()
            return self._dense_search_rows(rows)
        except Exception as error:
            raise PgVectorStoreError(
                f"PostgreSQL pgvector 유사도 검색 실패 ({collection_name}): {error}"
            ) from error
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    @staticmethod
    def _dense_search_query(
        *,
        collection_uuid: str,
        embedding: Sequence[float],
        k: int,
        sheet_names: Optional[Sequence[str]],
        company_name: Optional[str],
    ) -> tuple[str, List[Any]]:
        """Build the shared sync/async exact-rerank query and bound parameters."""
        canonical_uuid = str(UUID(collection_uuid))
        dim = len(embedding)
        vector_param = "[" + ",".join(format(float(value), ".17g") for value in embedding) + "]"
        where_clauses = [f"collection_id = '{canonical_uuid}'::uuid"]
        params: List[Any] = []
        if 0 < dim <= 64_000:
            candidate_limit = min(max(k * 20, 100), 1000)
            index_where_sql = (
                f"collection_id = '{canonical_uuid}'::uuid AND vector_dims(embedding) = {dim}"
            )
            outer_where_clauses: List[str] = []
            outer_params: List[Any] = []
            if company_name and company_name.strip():
                clean_company = company_name.strip()
                escaped_company = _escape_like_term(clean_company)
                outer_where_clauses.append(
                    "(cmetadata->>'company_name' ILIKE %s ESCAPE '!' "
                    "OR cmetadata->>'company_name' = %s)"
                )
                outer_params.extend([f"%{escaped_company}%", clean_company])
            if sheet_names:
                valid_sheets = [
                    sheet.strip()
                    for sheet in sheet_names
                    if isinstance(sheet, str) and sheet.strip()
                ]
                if valid_sheets:
                    outer_where_clauses.append("(cmetadata->>'sheet_name' = ANY(%s))")
                    outer_params.append(valid_sheets)
            outer_where_sql = (
                f"WHERE {' AND '.join(outer_where_clauses)}" if outer_where_clauses else ""
            )
            return (
                f"""
                WITH query_vector AS MATERIALIZED (
                    SELECT %s::vector AS embedding
                ), candidates AS MATERIALIZED (
                    SELECT id, document, cmetadata, source.embedding
                    FROM langchain_pg_embedding AS source
                    WHERE {index_where_sql}
                    ORDER BY
                        binary_quantize(source.embedding)::bit({dim})
                        <~> binary_quantize(
                            (SELECT embedding FROM query_vector)
                        )::bit({dim})
                    LIMIT %s
                )
                SELECT id, document, cmetadata,
                       candidates.embedding <=> query_vector.embedding AS distance
                FROM candidates
                CROSS JOIN query_vector
                {outer_where_sql}
                ORDER BY candidates.embedding <=> query_vector.embedding
                LIMIT %s;
                """,
                [vector_param, candidate_limit, *outer_params, k],
            )

        if company_name and company_name.strip():
            clean_company = company_name.strip()
            escaped_company = _escape_like_term(clean_company)
            where_clauses.append(
                "(cmetadata->>'company_name' ILIKE %s ESCAPE '!' "
                "OR cmetadata->>'company_name' = %s)"
            )
            params.extend([f"%{escaped_company}%", clean_company])
        if sheet_names:
            valid_sheets = [
                sheet.strip() for sheet in sheet_names if isinstance(sheet, str) and sheet.strip()
            ]
            if valid_sheets:
                where_clauses.append("(cmetadata->>'sheet_name' = ANY(%s))")
                params.append(valid_sheets)
        where_sql = " AND ".join(where_clauses)
        return (
            f"""
            SELECT id, document, cmetadata, (embedding <=> %s::vector) AS distance
            FROM langchain_pg_embedding
            WHERE {where_sql}
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
            """,
            [vector_param, *params, vector_param, k],
        )

    @staticmethod
    def _dense_search_rows(
        rows: Sequence[Sequence[Any]],
    ) -> List[Tuple[Document, float]]:
        import json

        results: List[Tuple[Document, float]] = []
        for row in rows:
            row_id, text, metadata, distance = row
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except Exception:
                    metadata = {}
            results.append(
                (
                    Document(
                        page_content=str(text or ""),
                        metadata=metadata if isinstance(metadata, dict) else {},
                        id=str(row_id),
                    ),
                    float(distance) if distance is not None else 0.0,
                )
            )
        return results

    async def similarity_search_by_vector_with_score_async(
        self,
        collection_name: str,
        embedding: Sequence[float],
        k: int = 10,
        *,
        sheet_names: Optional[Sequence[str]] = None,
        company_name: Optional[str] = None,
    ) -> List[Tuple[Document, float]]:
        """Run the collection-local HNSW query through native psycopg async I/O."""
        try:
            collection_uuid = await self._collection_uuid_async(collection_name)
            if collection_uuid is None:
                return []
            query_sql, params = self._dense_search_query(
                collection_uuid=collection_uuid,
                embedding=embedding,
                k=k,
                sheet_names=sheet_names,
                company_name=company_name,
            )
            raw_url = getattr(self, "database_url", PGVECTOR_URL).replace(
                "postgresql+psycopg://",
                "postgresql://",
            )
            async with get_pooled_async_connection(raw_url) as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(query_sql, params)  # type: ignore[arg-type]
                    rows = await cursor.fetchall()
            return self._dense_search_rows(rows)
        except Exception as error:
            raise PgVectorStoreError(
                f"PostgreSQL pgvector 유사도 검색 실패 ({collection_name}): {error}"
            ) from error

    @staticmethod
    def _cell_search_targets(clean_ids: Sequence[str]) -> List[str]:
        extracted_coords: List[str] = []
        for cell_id in clean_ids:
            parts = cell_id.replace(":", " ").replace("!", " ").split()
            for part in parts:
                candidate = part.strip()
                if (
                    candidate
                    and candidate[0].isalpha()
                    and any(character.isdigit() for character in candidate)
                ):
                    extracted_coords.append(candidate.upper())
        return list(dict.fromkeys(item.upper() for item in [*clean_ids, *extracted_coords]))

    @staticmethod
    def _group_cell_references(
        cell_references: Sequence[Dict[str, Optional[str]]],
    ) -> Dict[str, List[str]]:
        groups: Dict[str, List[str]] = {
            "triple_companies": [],
            "triple_sheets": [],
            "triple_coords": [],
            "sheet_pair_sheets": [],
            "sheet_pair_coords": [],
            "company_pair_companies": [],
            "company_pair_coords": [],
            "unqualified_coords": [],
        }
        for reference in cell_references:
            coord = (reference.get("cell_coord") or "").strip().upper()
            if not coord:
                continue
            sheet = (reference.get("sheet_name") or "").strip().upper()
            company = (reference.get("company_name") or "").strip().upper()
            if company and sheet:
                groups["triple_companies"].append(company)
                groups["triple_sheets"].append(sheet)
                groups["triple_coords"].append(coord)
            elif sheet:
                groups["sheet_pair_sheets"].append(sheet)
                groups["sheet_pair_coords"].append(coord)
            elif company:
                groups["company_pair_companies"].append(company)
                groups["company_pair_coords"].append(coord)
            else:
                groups["unqualified_coords"].append(coord)
        return groups

    @staticmethod
    def _cell_reference_predicates(
        groups: Dict[str, List[str]],
    ) -> tuple[List[str], List[Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        if groups["unqualified_coords"]:
            clauses.append("UPPER(cmetadata->>'cell_coord') = ANY(%s)")
            params.append(list(dict.fromkeys(groups["unqualified_coords"])))
        if groups["sheet_pair_coords"]:
            clauses.append(
                """EXISTS (
                    SELECT 1
                    FROM unnest(%s::text[], %s::text[])
                        AS reference(sheet_name, cell_coord)
                    WHERE UPPER(cmetadata->>'sheet_name') = reference.sheet_name
                      AND UPPER(cmetadata->>'cell_coord') = reference.cell_coord
                )"""
            )
            params.extend([groups["sheet_pair_sheets"], groups["sheet_pair_coords"]])
        if groups["company_pair_coords"]:
            clauses.append(
                """EXISTS (
                    SELECT 1
                    FROM unnest(%s::text[], %s::text[])
                        AS reference(company_name, cell_coord)
                    WHERE UPPER(COALESCE(cmetadata->>'company_name', '')) = reference.company_name
                      AND UPPER(cmetadata->>'cell_coord') = reference.cell_coord
                )"""
            )
            params.extend([groups["company_pair_companies"], groups["company_pair_coords"]])
        if groups["triple_coords"]:
            clauses.append(
                """EXISTS (
                    SELECT 1
                    FROM unnest(%s::text[], %s::text[], %s::text[])
                        AS reference(company_name, sheet_name, cell_coord)
                    WHERE UPPER(COALESCE(cmetadata->>'company_name', '')) = reference.company_name
                      AND UPPER(cmetadata->>'sheet_name') = reference.sheet_name
                      AND UPPER(cmetadata->>'cell_coord') = reference.cell_coord
                )"""
            )
            params.extend(
                [
                    groups["triple_companies"],
                    groups["triple_sheets"],
                    groups["triple_coords"],
                ]
            )
        return clauses, params

    @classmethod
    def _cell_metadata_query(
        cls,
        *,
        clean_ids: Sequence[str],
        workbook_hash: Optional[str],
        company_name: Optional[str],
        collection_uuid: Optional[str],
        limit: int,
        cell_references: Optional[Sequence[Dict[str, Optional[str]]]],
    ) -> Optional[tuple[str, List[Any]]]:
        search_targets = cls._cell_search_targets(clean_ids)
        if cell_references is None:
            where_clauses = [
                """(
                    cmetadata->>'cell_id' = ANY(%s)
                    OR cmetadata->>'cell_coord' = ANY(%s)
                    OR UPPER(cmetadata->>'cell_coord') = ANY(%s)
                )"""
            ]
            params: List[Any] = [list(clean_ids), search_targets, search_targets]
        else:
            groups = cls._group_cell_references(cell_references)
            where_clauses, params = cls._cell_reference_predicates(groups)
            if not where_clauses:
                return None

        query = f"""
            WITH ranked_cells AS (
            SELECT
                id,
                document,
                cmetadata,
                cmetadata->>'cell_id' AS cell_id,
                cmetadata->>'cell_coord' AS cell_coord,
                cmetadata->>'sheet_name' AS sheet_name,
                cmetadata->>'cell_value' AS cell_value,
                cmetadata->'row_header' AS row_header,
                cmetadata->'column_header' AS column_header,
                cmetadata->>'company_name' AS company_name,
                ROW_NUMBER() OVER (
                    PARTITION BY
                        UPPER(COALESCE(cmetadata->>'company_name', '')),
                        UPPER(cmetadata->>'sheet_name'),
                        UPPER(cmetadata->>'cell_coord')
                    ORDER BY
                        CASE
                            WHEN document NOT LIKE '%%Cell Value: ?%%' AND document NOT LIKE '%%Cell Value: NA%%' AND NULLIF(cmetadata->>'cell_value', '') IS NOT NULL AND cmetadata->>'cell_value' NOT IN ('?', 'NA') THEN 0
                            WHEN cmetadata->>'variant' = 'header_with_value' THEN 1
                            WHEN document NOT LIKE '%%Cell Value: ?%%' THEN 2
                            WHEN cmetadata->>'variant' = 'header_only' THEN 3
                            ELSE 4
                        END,
                        CASE WHEN jsonb_typeof(cmetadata->'row_header') = 'array'
                            THEN jsonb_array_length(cmetadata->'row_header') ELSE 0 END DESC,
                        CASE WHEN jsonb_typeof(cmetadata->'column_header') = 'array'
                            THEN jsonb_array_length(cmetadata->'column_header') ELSE 0 END DESC,
                        id
                ) AS cell_rank
            FROM langchain_pg_embedding
            WHERE ({" OR ".join(where_clauses)})
        """
        if collection_uuid:
            query += " AND collection_id = %s"
            params.append(collection_uuid)
        elif workbook_hash:
            query += " AND cmetadata->>'workbook_hash' = %s"
            params.append(workbook_hash)
        if company_name and company_name.strip():
            query += " AND UPPER(cmetadata->>'company_name') = %s"
            params.append(company_name.strip().upper())
        query += """
            )
            SELECT
                id,
                document,
                cmetadata,
                COALESCE(cell_id, sheet_name || ' Cell ' || cell_coord) AS cell_id,
                cell_coord,
                sheet_name,
                cell_value,
                row_header,
                column_header,
                company_name
            FROM ranked_cells
            WHERE cell_rank = 1
            ORDER BY
                CASE WHEN COALESCE(cell_id, sheet_name || ' Cell ' || cell_coord) = ANY(%s) THEN 0 ELSE 1 END,
                UPPER(sheet_name),
                UPPER(cell_coord),
                id
            LIMIT %s;
        """
        params.extend([list(clean_ids), limit])
        return query, params

    @staticmethod
    def _cell_metadata_rows(
        rows: Sequence[Sequence[Any]],
    ) -> List[Dict[str, Any]]:
        import json

        results: List[Dict[str, Any]] = []
        for row in rows:
            (
                _row_id,
                text,
                _metadata,
                cell_id,
                cell_coord,
                sheet_name,
                cell_value,
                row_header,
                column_header,
                company_name,
            ) = row
            metadata = _metadata if isinstance(_metadata, dict) else {}
            if isinstance(_metadata, str):
                try:
                    metadata = json.loads(_metadata)
                except Exception:
                    metadata = {}
            if isinstance(row_header, str):
                try:
                    row_header = json.loads(row_header)
                except Exception:
                    pass
            if isinstance(column_header, str):
                try:
                    column_header = json.loads(column_header)
                except Exception:
                    pass
            results.append(
                {
                    "cell_id": cell_id or f"{sheet_name}:{cell_coord}",
                    "cell_coord": cell_coord,
                    "sheet_name": sheet_name,
                    "cell_value": cell_value,
                    "row_header": (
                        row_header
                        if isinstance(row_header, list)
                        else ([row_header] if row_header else [])
                    ),
                    "column_header": (
                        column_header
                        if isinstance(column_header, list)
                        else ([column_header] if column_header else [])
                    ),
                    "company_name": company_name,
                    "file_name": metadata.get("file_name", ""),
                    "workbook_hash": metadata.get("workbook_hash", ""),
                    "index_id": metadata.get("index_id", ""),
                    "source_text": text,
                }
            )
        return results

    async def fetch_cells_by_metadata_async(
        self,
        cell_identifiers: Sequence[str],
        workbook_hash: Optional[str] = None,
        company_name: Optional[str] = None,
        collection_name: Optional[str] = None,
        limit: int = 50,
        cell_references: Optional[Sequence[Dict[str, Optional[str]]]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch qualified cells through native async PostgreSQL I/O."""
        if not cell_identifiers or not (workbook_hash or collection_name or company_name):
            return []
        clean_ids = [cell_id.strip() for cell_id in cell_identifiers if cell_id and cell_id.strip()]
        if not clean_ids:
            return []
        collection_uuid = (
            await self._collection_uuid_async(collection_name) if collection_name else None
        )
        if collection_name and collection_uuid is None and not (workbook_hash or company_name):
            return []
        query_spec = self._cell_metadata_query(
            clean_ids=clean_ids,
            workbook_hash=workbook_hash,
            company_name=company_name,
            collection_uuid=collection_uuid,
            limit=limit,
            cell_references=cell_references,
        )
        if query_spec is None:
            return []
        query, params = query_spec
        raw_url = getattr(self, "database_url", PGVECTOR_URL).replace(
            "postgresql+psycopg://",
            "postgresql://",
        )
        try:
            async with get_pooled_async_connection(raw_url) as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(query, params)  # type: ignore[arg-type]
                    rows = await cursor.fetchall()
            return self._cell_metadata_rows(rows)
        except Exception:
            logger.exception("비동기 직접 셀 메타데이터 조회 실패")
            return []

    def fetch_cells_by_metadata(
        self,
        cell_identifiers: List[str],
        workbook_hash: Optional[str] = None,
        company_name: Optional[str] = None,
        collection_name: Optional[str] = None,
        limit: int = 50,
        cell_references: Optional[List[Dict[str, Optional[str]]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch cell documents matching the provided identifiers, optionally filtered by workbook, company, or collection.

        Parameters:
            cell_identifiers (List[str]): Cell IDs, coordinates, or strings containing coordinate-like values.
            workbook_hash (Optional[str]): Restricts results to a workbook with this hash.
            company_name (Optional[str]): Restricts results to this company name.
            collection_name (Optional[str]): Restricts results to this collection.
            limit (int): Maximum number of matching cells to return.
            cell_references (Optional[List[Dict[str, Optional[str]]]]): Structured
                coordinate filters whose optional ``sheet_name`` and ``company_name``
                are matched together with the coordinate.

        Returns:
            List[Dict[str, Any]]: Normalized cell records containing identifiers, values, headers, source text, and company metadata. Returns an empty list when the input is empty or retrieval fails.
        """
        if not cell_identifiers or not (workbook_hash or collection_name or company_name):
            if cell_identifiers:
                logger.warning(
                    "직접 셀 메타데이터 조회를 거부했습니다: collection_name, workbook_hash 또는 company_name이 필요합니다"
                )
            return []
        clean_ids = [cell_id.strip() for cell_id in cell_identifiers if cell_id and cell_id.strip()]
        if not clean_ids:
            return []
        collection_uuid = self._collection_uuid(collection_name) if collection_name else None
        if collection_name and collection_uuid is None and not (workbook_hash or company_name):
            return []
        query_spec = self._cell_metadata_query(
            clean_ids=clean_ids,
            workbook_hash=workbook_hash,
            company_name=company_name,
            collection_uuid=collection_uuid,
            limit=limit,
            cell_references=cell_references,
        )
        if query_spec is None:
            return []
        query, params = query_spec
        connection = self._raw_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        except Exception:
            logger.exception("직접 셀 메타데이터 조회 실패")
            return []
        finally:
            connection.close()
        return self._cell_metadata_rows(rows)

    def fetch_adjacent_row_cells(
        self,
        collection_name: Optional[str] = None,
        workbook_hash: Optional[str] = None,
        sheet_name: Optional[str] = None,
        row_index: Optional[int] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Fetch all cells on a given row index within a sheet and collection for horizontal timeseries expansion."""
        if not (collection_name or workbook_hash) or row_index is None:
            return []
        return self.fetch_rows_cells(
            collection_name=collection_name,
            workbook_hash=workbook_hash,
            sheet_name=sheet_name,
            row_indices=[row_index],
            limit_per_row=limit,
        ).get(row_index, [])

    @staticmethod
    def _rows_cells_query(
        *,
        collection_name: Optional[str],
        workbook_hash: Optional[str],
        sheet_name: Optional[str],
        row_indices: Sequence[int],
    ) -> Optional[tuple[str, List[Any]]]:
        unique_rows = sorted({row for row in row_indices if row > 0})
        if not unique_rows or not (collection_name or workbook_hash):
            return None
        collection_names = (
            [name.strip() for name in collection_name.split(",") if name.strip()]
            if collection_name
            else []
        )
        scope_clauses: List[str] = []
        scope_params: List[Any] = []
        cte_params: List[Any] = []
        if collection_names:
            collection_cte_sql = (
                "target_collections AS ("
                "SELECT uuid FROM langchain_pg_collection WHERE name = ANY(%s)"
                "),"
            )
            cte_params.append(collection_names)
            scope_clauses.append("collection_id IN (SELECT uuid FROM target_collections)")
        else:
            collection_cte_sql = ""
        if workbook_hash and not collection_names:
            workbook_hashes = [value.strip() for value in workbook_hash.split(",") if value.strip()]
            scope_clauses.append("cmetadata->>'workbook_hash' = ANY(%s)")
            scope_params.append(workbook_hashes)
        if sheet_name:
            scope_clauses.append("cmetadata->>'sheet_name' = %s")
            scope_params.append(sheet_name)
        scope_sql = " AND " + " AND ".join(scope_clauses) if scope_clauses else ""
        return (
            rf"""
            WITH {collection_cte_sql}
            filtered_rows AS (
                SELECT
                    id,
                    document,
                    cmetadata,
                    COALESCE(
                        CASE WHEN cmetadata->>'row_index' ~ '^\d+$' THEN (cmetadata->>'row_index')::int ELSE NULL END,
                        NULLIF(regexp_replace(cmetadata->>'cell_coord', '[^0-9]', '', 'g'), '')::int
                    ) AS resolved_row_index,
                    CASE
                        WHEN cmetadata->>'col_index' ~ '^\d+$'
                            THEN (cmetadata->>'col_index')::int
                        ELSE NULL
                    END AS resolved_col_index,
                    ROW_NUMBER() OVER (
                        PARTITION BY COALESCE(
                            CASE WHEN cmetadata->>'row_index' ~ '^\d+$' THEN (cmetadata->>'row_index')::int ELSE NULL END,
                            NULLIF(regexp_replace(cmetadata->>'cell_coord', '[^0-9]', '', 'g'), '')::int
                        ),
                        cmetadata->>'cell_coord'
                        ORDER BY
                            CASE WHEN cmetadata->>'variant' = 'header_with_value' THEN 0 ELSE 1 END,
                            CASE WHEN jsonb_typeof(cmetadata->'row_header') = 'array'
                                THEN jsonb_array_length(cmetadata->'row_header') ELSE 0 END DESC,
                            CASE WHEN jsonb_typeof(cmetadata->'column_header') = 'array'
                                THEN jsonb_array_length(cmetadata->'column_header') ELSE 0 END DESC,
                            CASE WHEN cmetadata->>'col_index' ~ '^\d+$' THEN (cmetadata->>'col_index')::int ELSE 99999 END,
                            id
                    ) AS coord_rank
                FROM langchain_pg_embedding
                WHERE (
                    (cmetadata->>'row_index' ~ '^\d+$' AND (cmetadata->>'row_index')::int = ANY(%s))
                    OR
                    (NULLIF(regexp_replace(cmetadata->>'cell_coord', '[^0-9]', '', 'g'), '') ~ '^\d+$'
                     AND (NULLIF(regexp_replace(cmetadata->>'cell_coord', '[^0-9]', '', 'g'), ''))::int = ANY(%s))
                )
                {scope_sql}
            )
            SELECT id, document, cmetadata, resolved_row_index, resolved_col_index
            FROM filtered_rows
            WHERE coord_rank = 1
            ORDER BY resolved_row_index,
                     cmetadata->>'cell_coord',
                     id;
            """,
            [*cte_params, unique_rows, unique_rows, *scope_params],
        )

    @staticmethod
    def _rows_cells_rows(
        rows: Sequence[Sequence[Any]],
        limit_per_row: int,
    ) -> Dict[int, List[Dict[str, Any]]]:
        from openpyxl.utils.cell import column_index_from_string

        results: Dict[int, List[Dict[str, Any]]] = {}
        for cell_id, document, metadata, resolved_row, resolved_col in rows:
            cmetadata = metadata if isinstance(metadata, dict) else {}
            col_idx = resolved_col
            if col_idx is None and cmetadata.get("cell_coord"):
                col_match = re.match(r"^([A-Za-z]+)", cmetadata.get("cell_coord", ""))
                if col_match:
                    try:
                        col_idx = column_index_from_string(col_match.group(1))
                    except Exception:
                        pass
            results.setdefault(int(resolved_row), []).append(
                {
                    "cell_id": cell_id or cmetadata.get("cell_id", ""),
                    "cell_coord": cmetadata.get("cell_coord", ""),
                    "cell_value": cmetadata.get("cell_value", ""),
                    "sheet_name": cmetadata.get("sheet_name", ""),
                    "row_header": cmetadata.get("row_header", []),
                    "column_header": cmetadata.get("column_header", []),
                    "company_name": cmetadata.get("company_name", ""),
                    "index_id": cmetadata.get("index_id", ""),
                    "workbook_hash": cmetadata.get("workbook_hash", ""),
                    "file_name": cmetadata.get("file_name", ""),
                    "row_index": resolved_row,
                    "col_index": col_idx,
                    "source_text": document or "",
                }
            )
        for row_index, row_cells in results.items():
            row_cells.sort(
                key=lambda cell: (
                    cell.get("col_index") is None,
                    cell.get("col_index") or 0,
                )
            )
            results[row_index] = row_cells[: max(1, limit_per_row)]
        return results

    async def fetch_rows_cells_async(
        self,
        *,
        collection_name: Optional[str],
        workbook_hash: Optional[str],
        sheet_name: Optional[str],
        row_indices: Sequence[int],
        limit_per_row: int = 50,
    ) -> Dict[int, List[Dict[str, Any]]]:
        """Fetch row context with native async PostgreSQL I/O."""
        query_spec = self._rows_cells_query(
            collection_name=collection_name,
            workbook_hash=workbook_hash,
            sheet_name=sheet_name,
            row_indices=row_indices,
        )
        if query_spec is None:
            return {}
        query_sql, params = query_spec
        raw_url = getattr(self, "database_url", PGVECTOR_URL).replace(
            "postgresql+psycopg://",
            "postgresql://",
        )
        try:
            async with get_pooled_async_connection(raw_url) as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(query_sql, params)  # type: ignore[arg-type]
                    rows = await cursor.fetchall()
            return self._rows_cells_rows(rows, limit_per_row)
        except Exception as error:
            logger.warning("fetch_rows_cells_async 실패: %s", error)
            return {}

    @staticmethod
    def _rows_cells_scope(
        collection_name: Optional[str],
        workbook_hash: Optional[str],
        sheet_name: Optional[str],
    ) -> tuple[str, List[Any], str, List[Any]]:
        collection_names = [
            name.strip() for name in (collection_name or "").split(",") if name.strip()
        ]
        clauses: List[str] = []
        scope_params: List[Any] = []
        cte_params: List[Any] = []
        collection_cte_sql = ""
        if collection_names:
            collection_cte_sql = (
                "target_collections AS ("
                "SELECT uuid FROM langchain_pg_collection WHERE name = ANY(%s)"
                "),"
            )
            cte_params.append(collection_names)
            clauses.append("collection_id IN (SELECT uuid FROM target_collections)")
        elif workbook_hash:
            hashes = [value.strip() for value in workbook_hash.split(",") if value.strip()]
            clauses.append("cmetadata->>'workbook_hash' = ANY(%s)")
            scope_params.append(hashes)
        if sheet_name:
            clauses.append("cmetadata->>'sheet_name' = %s")
            scope_params.append(sheet_name)
        scope_sql = " AND " + " AND ".join(clauses) if clauses else ""
        return collection_cte_sql, cte_params, scope_sql, scope_params

    def fetch_rows_cells(
        self,
        collection_name: Optional[str],
        workbook_hash: Optional[str],
        sheet_name: Optional[str],
        row_indices: List[int],
        limit_per_row: int = 50,
    ) -> Dict[int, List[Dict[str, Any]]]:
        """Fetch several rows in one SQL round trip, bounded per requested row."""
        unique_rows = sorted({row for row in row_indices if row > 0})
        if not unique_rows or not (collection_name or workbook_hash):
            return {}
        conn = self._read_connection()
        try:
            with conn.cursor() as cur:
                collection_cte_sql, cte_params, scope_sql, scope_params = self._rows_cells_scope(
                    collection_name, workbook_hash, sheet_name
                )

                query_sql = f"""
                    WITH {collection_cte_sql}
                    filtered_rows AS (
                        SELECT
                            id,
                            document,
                            cmetadata,
                            COALESCE(
                                CASE WHEN cmetadata->>'row_index' ~ '^\\d+$' THEN (cmetadata->>'row_index')::int ELSE NULL END,
                                NULLIF(regexp_replace(cmetadata->>'cell_coord', '[^0-9]', '', 'g'), '')::int
                            ) AS resolved_row_index,
                            CASE
                                WHEN cmetadata->>'col_index' ~ '^\\d+$'
                                    THEN (cmetadata->>'col_index')::int
                                ELSE NULL
                            END AS resolved_col_index,
                            ROW_NUMBER() OVER (
                                PARTITION BY COALESCE(
                                    CASE WHEN cmetadata->>'row_index' ~ '^\\d+$' THEN (cmetadata->>'row_index')::int ELSE NULL END,
                                    NULLIF(regexp_replace(cmetadata->>'cell_coord', '[^0-9]', '', 'g'), '')::int
                                ),
                                cmetadata->>'cell_coord'
                                ORDER BY
                                    CASE WHEN cmetadata->>'variant' = 'header_with_value' THEN 0 ELSE 1 END,
                                    CASE WHEN jsonb_typeof(cmetadata->'row_header') = 'array'
                                        THEN jsonb_array_length(cmetadata->'row_header') ELSE 0 END DESC,
                                    CASE WHEN jsonb_typeof(cmetadata->'column_header') = 'array'
                                        THEN jsonb_array_length(cmetadata->'column_header') ELSE 0 END DESC,
                                    CASE WHEN cmetadata->>'col_index' ~ '^\\d+$' THEN (cmetadata->>'col_index')::int ELSE 99999 END,
                                    id
                            ) AS coord_rank
                        FROM langchain_pg_embedding
                        WHERE (
                            (cmetadata->>'row_index' ~ '^\\d+$' AND (cmetadata->>'row_index')::int = ANY(%s))
                            OR
                            (NULLIF(regexp_replace(cmetadata->>'cell_coord', '[^0-9]', '', 'g'), '') ~ '^\\d+$'
                             AND (NULLIF(regexp_replace(cmetadata->>'cell_coord', '[^0-9]', '', 'g'), ''))::int = ANY(%s))
                        )
                        {scope_sql}
                    )
                    SELECT id, document, cmetadata, resolved_row_index, resolved_col_index
                    FROM filtered_rows
                    WHERE coord_rank = 1
                    ORDER BY resolved_row_index,
                             cmetadata->>'cell_coord',
                             id;
                """
                params = [
                    *cte_params,
                    unique_rows,
                    unique_rows,
                    *scope_params,
                ]
                cur.execute(query_sql, tuple(params))
                return self._rows_cells_rows(cur.fetchall(), limit_per_row)
        except Exception as err:
            logger.warning("fetch_rows_cells 실패: %s", err)
            return {}
        finally:
            conn.close()


__all__ = ["PgVectorRetrievalMixin"]
