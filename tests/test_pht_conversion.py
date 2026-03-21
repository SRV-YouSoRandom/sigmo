"""Tests for PHT timezone boundary helpers in app.core.config."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.core.config import PHT, pht_today_start_utc, to_pht


# ---------------------------------------------------------------------------
# to_pht
# ---------------------------------------------------------------------------

def test_to_pht_converts_naive_utc():
    """Naive UTC datetime should be treated as UTC and converted to UTC+8."""
    utc_dt = datetime(2026, 1, 1, 0, 0, 0)  # midnight UTC
    pht_dt = to_pht(utc_dt)
    assert pht_dt.hour == 8
    assert pht_dt.day == 1


def test_to_pht_converts_aware_utc():
    """Timezone-aware UTC datetime should also convert correctly."""
    utc_dt = datetime(2026, 1, 1, 16, 0, 0, tzinfo=timezone.utc)
    pht_dt = to_pht(utc_dt)
    assert pht_dt.hour == 0
    assert pht_dt.day == 2  # midnight PHT of Jan 2


def test_to_pht_offset_is_8_hours():
    """PHT should always be exactly UTC+8."""
    utc_dt = datetime(2026, 6, 15, 10, 30, 0)
    pht_dt = to_pht(utc_dt)
    assert pht_dt.hour == 18
    assert pht_dt.minute == 30


# ---------------------------------------------------------------------------
# pht_today_start_utc — the core bug fix
# ---------------------------------------------------------------------------

def test_pht_today_start_utc_returns_naive():
    """Result must be a naive datetime (no tzinfo) for DB query compatibility."""
    result = pht_today_start_utc()
    assert result.tzinfo is None


def test_pht_today_start_utc_is_midnight_of_pht_day():
    """The result, when converted back to PHT, should be exactly midnight."""
    result = pht_today_start_utc()
    # Attach UTC tzinfo and convert to PHT
    result_as_pht = result.replace(tzinfo=timezone.utc).astimezone(PHT)
    assert result_as_pht.hour == 0
    assert result_as_pht.minute == 0
    assert result_as_pht.second == 0


def test_pht_today_start_utc_before_0800_utc():
    """
    The critical bug case: between 00:00–08:00 UTC (= 08:00–16:00 PHT),
    UTC is still on the previous calendar date. The old calculation would
    overshoot by a full day. This test verifies the correct boundary.

    Scenario: it's 06:00 UTC on Jan 2 = 14:00 PHT on Jan 2.
    PHT today midnight = 00:00 PHT Jan 2 = 16:00 UTC Jan 1.
    """
    fake_now_utc = datetime(2026, 1, 2, 6, 0, 0)  # 06:00 UTC Jan 2 = 14:00 PHT Jan 2
    with patch("app.core.config.datetime") as mock_dt:
        mock_dt.utcnow.return_value = fake_now_utc
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = pht_today_start_utc()

    # Should be 16:00 UTC Jan 1 (= midnight PHT Jan 2)
    assert result == datetime(2026, 1, 1, 16, 0, 0)


def test_pht_today_start_utc_after_1600_utc():
    """
    After 16:00 UTC (= midnight PHT next day), the PHT day has rolled over.

    Scenario: it's 17:00 UTC on Jan 1 = 01:00 PHT on Jan 2.
    PHT today midnight = 00:00 PHT Jan 2 = 16:00 UTC Jan 1.
    """
    fake_now_utc = datetime(2026, 1, 1, 17, 0, 0)  # 17:00 UTC Jan 1 = 01:00 PHT Jan 2
    with patch("app.core.config.datetime") as mock_dt:
        mock_dt.utcnow.return_value = fake_now_utc
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = pht_today_start_utc()

    # Should be 16:00 UTC Jan 1 (= midnight PHT Jan 2)
    assert result == datetime(2026, 1, 1, 16, 0, 0)


def test_pht_today_start_utc_old_bug_would_fail():
    """
    Explicitly demonstrates the old bug.

    At 06:00 UTC Jan 2, the old calculation:
      datetime.utcnow().replace(hour=0) - timedelta(hours=8)
      = Jan 2 00:00 UTC - 8h
      = Jan 1 16:00 UTC  ← accidentally correct only because replace() gives Jan 2

    But at 07:00 UTC Jan 2 (still before PHT midnight rollover at 16:00 UTC):
      Same calculation still gives Jan 1 16:00 UTC — actually fine here too.

    The real failure was the OPPOSITE scenario — it included yesterday's runs.
    This test documents the expected correct value to prevent regression.
    """
    # 23:00 UTC Jan 1 = 07:00 PHT Jan 2 (early morning PHT)
    fake_now_utc = datetime(2026, 1, 1, 23, 0, 0)
    with patch("app.core.config.datetime") as mock_dt:
        mock_dt.utcnow.return_value = fake_now_utc
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = pht_today_start_utc()

    # 07:00 PHT Jan 2 → PHT today is Jan 2 → midnight PHT Jan 2 = 16:00 UTC Jan 1
    assert result == datetime(2026, 1, 0o1, 16, 0, 0)

    # What the OLD buggy code would have returned:
    old_buggy_result = (
        fake_now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        - timedelta(hours=8)
    )
    # Old code: Jan 1 00:00 UTC - 8h = Dec 31 16:00 UTC — a full day too early!
    assert old_buggy_result == datetime(2025, 12, 31, 16, 0, 0)
    assert old_buggy_result != result  # proves the old code was wrong