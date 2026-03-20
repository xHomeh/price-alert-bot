from __future__ import annotations

from sqlalchemy.dialects import postgresql

from carousell_alert_bot.db.models import ScanRun, ScanRunStatus, Watch, WatchStatus


def test_watch_status_enum_binds_lowercase_values() -> None:
    enum_type = Watch.__table__.c.status.type
    processor = enum_type.bind_processor(postgresql.dialect())

    assert enum_type.enums == ["active", "paused", "deleted"]
    assert processor is not None
    assert processor(WatchStatus.ACTIVE) == "active"


def test_scan_run_status_enum_binds_lowercase_values() -> None:
    enum_type = ScanRun.__table__.c.status.type
    processor = enum_type.bind_processor(postgresql.dialect())

    assert enum_type.enums == ["started", "success", "failed"]
    assert processor is not None
    assert processor(ScanRunStatus.STARTED) == "started"
