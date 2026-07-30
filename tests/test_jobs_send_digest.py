from datetime import datetime

from ea_alert.db import Store
from ea_alert.jobs import send_digest
from ea_alert.models import JST, KIND_INDICATOR, Event
from tests.fakes import FakeNotifier
from tests.test_jobs_fetch_daily import make_config


def make_indicator(title, importance=3, country="米国", hour=21, minute=30, day=31):
    return Event(
        kind=KIND_INDICATOR,
        datetime_jst=datetime(2026, 7, day, hour, minute, tzinfo=JST),
        time_known=True,
        country=country,
        title=title,
        importance=importance,
    )


def test_digest_sends_filtered_events(tmp_path):
    config = make_config(tmp_path)
    store = Store(config.db_path)
    notifier = FakeNotifier()
    store.upsert_events([
        make_indicator("米GDP", importance=3),
        make_indicator("トルコCPI", importance=3, country="トルコ"),  # 対象外通貨
        make_indicator("低重要度", importance=1),                      # 重要度不足
        make_indicator("別日分", day=1),  # 7/1 → 当日(7/31)ではない
    ])
    now = datetime(2026, 7, 31, 9, 0, tzinfo=JST)

    send_digest.run(config, store, notifier, now)

    assert len(notifier.broadcasts) == 1
    text = notifier.broadcasts[0]
    assert "米GDP" in text
    assert "トルコCPI" not in text
    assert "低重要度" not in text
    assert "別日分" not in text


def test_digest_is_idempotent(tmp_path):
    config = make_config(tmp_path)
    store = Store(config.db_path)
    notifier = FakeNotifier()
    store.upsert_events([make_indicator("米GDP")])
    now = datetime(2026, 7, 31, 9, 0, tzinfo=JST)

    send_digest.run(config, store, notifier, now)
    send_digest.run(config, store, notifier, now)  # 再実行しても送らない

    assert len(notifier.broadcasts) == 1


def test_digest_skips_when_no_events(tmp_path):
    config = make_config(tmp_path)
    store = Store(config.db_path)
    notifier = FakeNotifier()
    now = datetime(2026, 7, 31, 9, 0, tzinfo=JST)

    send_digest.run(config, store, notifier, now)

    assert notifier.broadcasts == []


def test_digest_respects_notices_flag(tmp_path):
    config = make_config(tmp_path)
    config.notices["digest"] = False
    store = Store(config.db_path)
    notifier = FakeNotifier()
    store.upsert_events([make_indicator("米GDP")])
    now = datetime(2026, 7, 31, 9, 0, tzinfo=JST)

    send_digest.run(config, store, notifier, now)

    assert notifier.broadcasts == []
