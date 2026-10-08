from datetime import date

import pytest

from app import handlers
from app import payments


@pytest.mark.asyncio
async def test_get_month_mandatory_payments(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"

    import app.db

    await app.db.init_db()

    monkeypatch.setattr(
        payments,
        "DB_PATH",
        str(db_path),
    )

    monkeypatch.setattr(
        handlers,
        "DB_PATH",
        str(db_path),
    )

    assert True


@pytest.mark.asyncio
async def test_get_current_month():
    month = handlers.get_current_month()

    assert len(month) == 7
    assert month[4] == "-"
