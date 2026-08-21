"""Focused tests for source-file deletion resolution."""

import pytest

from backend.storage.db_manager import DatabaseManager


class FakeCursor:
    def __init__(self, *, direct_deleted=0, filename_matches=()):
        self.direct_deleted = direct_deleted
        self.filename_matches = list(filename_matches)
        self.rowcount = 0
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, params=None):
        """
        Record a normalized query and update the simulated affected-row count.
        
        Parameters:
        	query (str): The SQL query to record.
        	params (object, optional): Parameters associated with the query.
        """
        normalized = " ".join(query.split())
        self.executions.append((normalized, params))
        if "WHERE file_id = %s OR file_hash = %s" in normalized:
            self.rowcount = self.direct_deleted
        elif normalized.startswith("DELETE FROM source_files WHERE file_id = %s"):
            self.rowcount = 1
        else:
            self.rowcount = 0

    def fetchmany(self, size):
        return self.filename_matches[:size]


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def database_with(cursor):
    database = DatabaseManager("postgresql://mock:5432/mock")
    connection = FakeConnection(cursor)
    database._raw_connection = lambda: connection
    return database, connection


def test_init_does_not_perform_db_io(monkeypatch):
    called = False

    def mock_connect(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("Connection should not be attempted on init")

    monkeypatch.setattr("psycopg2.connect", mock_connect)
    manager = DatabaseManager("postgresql://mock:5432/mock")
    assert manager.database_url == "postgresql://mock:5432/mock"
    assert called is False


def test_delete_source_file_resolves_unique_filename_to_one_id():
    cursor = FakeCursor(filename_matches=[("file-id-1",)])
    database, connection = database_with(cursor)

    assert database.delete_source_file("folder/sample.xlsx") is True
    assert cursor.executions[-1][1] == ("file-id-1",)
    assert connection.committed is True
    assert connection.closed is True


def test_delete_source_file_rejects_ambiguous_filename():
    cursor = FakeCursor(filename_matches=[("file-id-1",), ("file-id-2",)])
    database, connection = database_with(cursor)

    with pytest.raises(ValueError, match="file_id 또는 file_hash"):
        database.delete_source_file("sample.xlsx")

    assert len(cursor.executions) == 2
    assert connection.committed is False
    assert connection.closed is True


def test_delete_source_file_keeps_direct_id_or_hash_deletion():
    cursor = FakeCursor(direct_deleted=1)
    database, connection = database_with(cursor)

    assert database.delete_source_file("a" * 64) is True
    assert len(cursor.executions) == 1
    assert "file_hash" in cursor.executions[0][0]
    assert connection.committed is True


def test_is_connected_success_closes_connection():
    cursor = FakeCursor()
    database, connection = database_with(cursor)

    assert database.is_connected() is True
    assert connection.closed is True


def test_is_connected_error_closes_connection():
    class ErrorCursor(FakeCursor):
        def execute(self, query, params=None):
            """Simulate a database execution failure.
            
            Raises:
                RuntimeError: Always, indicating that the database connection was lost.
            """
            raise RuntimeError("DB connection lost")

    cursor = ErrorCursor()
    database, connection = database_with(cursor)

    assert database.is_connected() is False
    assert connection.closed is True


def test_ensure_schema_closes_connection_on_success():
    cursor = FakeCursor()
    database, connection = database_with(cursor)

    database.ensure_schema()
    assert connection.committed is True
    assert connection.closed is True
    # Ensure no destructive ALTER TABLE DROP COLUMN in ensure_schema
    executed_queries = " ".join(e[0] for e in cursor.executions)
    assert "DROP COLUMN" not in executed_queries


def test_ensure_schema_logs_and_closes_connection_on_error():
    class ErrorCursor(FakeCursor):
        def execute(self, query, params=None):
            raise RuntimeError("Schema init error")

    cursor = ErrorCursor()
    database, connection = database_with(cursor)

    database.ensure_schema()
    assert connection.committed is False
    assert connection.closed is True


def test_run_migrations_closes_connection_on_success():
    cursor = FakeCursor()
    database, connection = database_with(cursor)

    database.run_migrations()
    assert connection.committed is True
    assert connection.closed is True
    executed_queries = " ".join(e[0] for e in cursor.executions)
    assert "DROP COLUMN IF EXISTS file_content" in executed_queries


def test_run_migrations_logs_and_closes_connection_on_error():
    class ErrorCursor(FakeCursor):
        def execute(self, query, params=None):
            raise RuntimeError("Migration error")

    cursor = ErrorCursor()
    database, connection = database_with(cursor)

    database.run_migrations()
    assert connection.committed is False
    assert connection.closed is True



