"""The app engine carries a database command timeout (real-DB behaviour in
``tests/integration/test_db_command_timeout.py``)."""

import importlib
from unittest.mock import MagicMock, patch

import app.db.session as session_module


def test_engine_is_created_with_a_command_timeout() -> None:
    with patch(
        "sqlalchemy.ext.asyncio.create_async_engine", return_value=MagicMock()
    ) as create:
        importlib.reload(session_module)
    importlib.reload(session_module)  # restore the real engine for other tests

    kwargs = create.call_args.kwargs
    assert kwargs["connect_args"] == {"command_timeout": 60}
    assert kwargs["pool_pre_ping"] is True
    assert session_module.DB_COMMAND_TIMEOUT_SECONDS == 60
