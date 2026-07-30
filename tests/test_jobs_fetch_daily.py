from datetime import datetime
from pathlib import Path

from ea_alert.config import Config
from ea_alert.db import Store
from ea_alert.fetchers.gaikaex import CALENDAR_URL
from ea_alert.jobs import fetch_daily
from ea_alert.models import JST, KIND_INDICATOR
from tests.fakes import FakeHttp, FakeNotifier

FIXTURE = Path(__file__).parent / "fixtures" / "gaikaex_calendar.html"


def make_config(tmp_path):
    return Config(
        currencies=["USD", "JPY", "EUR", "GBP"],
        digest_min_importance=2,
        pre_indicator_min_importance=3,
        pre_indicator_minutes=30,
        pre_speech_minutes=120,
        notices={"digest": True, "pre_indicator": True, "pre_speech": True, "statement": True},
        line_token="t",
        admin_user_id="U1",
        db_path=str(tmp_path / "t.db"),
    )


def test_fetch_daily_stores_today_and_tomorrow(tmp_path):
    config = make_config(tmp_path)
    store = Store(config.db_path)
    notifier = FakeNotifier()
    http_get = FakeHttp({CALENDAR_URL: FIXTURE.read_text(encoding="utf-8")})
    now = datetime(2026, 7, 30, 6, 0, tzinfo=JST)

    fetch_daily.run(config, store, notifier, http_get, now)

    today_events = store.events_between(
        datetime(2026, 7, 30, 0, 0, tzinfo=JST),
        datetime(2026, 7, 30, 23, 59, tzinfo=JST),
        kind=KIND_INDICATOR,
    )
    tomorrow_events = store.events_between(
        datetime(2026, 7, 31, 0, 0, tzinfo=JST),
        datetime(2026, 7, 31, 23, 59, tzinfo=JST),
        kind=KIND_INDICATOR,
    )
    assert len(today_events) > 0
    assert len(tomorrow_events) > 0
    # 2日より先は保存しない
    later = store.events_between(
        datetime(2026, 8, 1, 0, 0, tzinfo=JST),
        datetime(2026, 12, 31, 0, 0, tzinfo=JST),
    )
    assert later == []
    assert notifier.admin_notices == []


def test_fetch_daily_alerts_admin_on_empty_parse(tmp_path):
    config = make_config(tmp_path)
    store = Store(config.db_path)
    notifier = FakeNotifier()
    http_get = FakeHttp({CALENDAR_URL: "<html><body>改修されました</body></html>"})
    now = datetime(2026, 7, 30, 6, 0, tzinfo=JST)

    fetch_daily.run(config, store, notifier, http_get, now)

    assert len(notifier.admin_notices) == 1
    assert "0件" in notifier.admin_notices[0]
