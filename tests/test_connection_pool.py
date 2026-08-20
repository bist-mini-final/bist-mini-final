import logging
from unittest.mock import MagicMock, PropertyMock

from backend.storage.connection_pool import PooledConnectionWrapper


def test_pooled_connection_wrapper_normal_close():
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_conn.autocommit = True

    wrapper = PooledConnectionWrapper(mock_pool, mock_conn)
    assert not wrapper.closed

    wrapper.close()

    assert mock_conn.autocommit is False
    mock_pool.putconn.assert_called_once_with(mock_conn)
    mock_conn.close.assert_not_called()
    assert wrapper.closed


def test_pooled_connection_wrapper_autocommit_restoration_failure(caplog):
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    
    type(mock_conn).autocommit = PropertyMock(
        side_effect=RuntimeError("Autocommit reset failed")
    )

    wrapper = PooledConnectionWrapper(mock_pool, mock_conn)
    with caplog.at_level(logging.ERROR):
        wrapper.close()

    mock_pool.putconn.assert_not_called()
    mock_conn.close.assert_called_once()
    assert wrapper.closed
    assert "autocommit 복구 실패" in caplog.text


def test_pooled_connection_wrapper_putconn_failure(caplog):
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_conn.autocommit = False
    mock_pool.putconn.side_effect = RuntimeError("Pool connection return failed")

    wrapper = PooledConnectionWrapper(mock_pool, mock_conn)
    with caplog.at_level(logging.ERROR):
        wrapper.close()

    mock_pool.putconn.assert_called_once_with(mock_conn)
    mock_conn.close.assert_called_once()
    assert wrapper.closed
    assert "putconn" in caplog.text


def test_pooled_connection_wrapper_close_idempotent():
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_conn.autocommit = False

    wrapper = PooledConnectionWrapper(mock_pool, mock_conn)
    wrapper.close()
    wrapper.close()

    assert mock_pool.putconn.call_count == 1
    assert wrapper.closed
