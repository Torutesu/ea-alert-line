from datetime import datetime

from ea_alert.db import Store
from ea_alert.models import JST, KIND_INDICATOR, KIND_SPEECH, Event


def make_event(**overrides):
    defaults = dict(
        kind=KIND_INDICATOR,
        datetime_jst=datetime(2026, 7, 31, 21, 30, tzinfo=JST),
        time_known=True,
        country="米国",
        title="4-6月期GDP速報値",
        importance=3,
        forecast="2.0%",
        previous="1.4%",
        source_url="https://example.com",
    )
    defaults.update(overrides)
    return Event(**defaults)


def test_upsert_and_roundtrip(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    e = make_event()
    store.upsert_events([e])
    got = store.events_between(
        datetime(2026, 7, 31, 0, 0, tzinfo=JST),
        datetime(2026, 7, 31, 23, 59, tzinfo=JST),
    )
    assert got == [e]


def test_upsert_is_idempotent(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    e = make_event()
    store.upsert_events([e])
    store.upsert_events([e])
    got = store.events_between(
        datetime(2026, 7, 31, 0, 0, tzinfo=JST),
        datetime(2026, 7, 31, 23, 59, tzinfo=JST),
    )
    assert len(got) == 1


def test_events_between_bounds_inclusive_and_kind_filter(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    ind = make_event()
    sp = make_event(
        kind=KIND_SPEECH, country="", title="会見",
        datetime_jst=datetime(2026, 7, 31, 21, 30, tzinfo=JST),
    )
    outside = make_event(title="翌日分", datetime_jst=datetime(2026, 8, 1, 9, 0, tzinfo=JST))
    store.upsert_events([ind, sp, outside])

    # 境界ちょうど（21:30〜21:30）は両端含む
    got = store.events_between(
        datetime(2026, 7, 31, 21, 30, tzinfo=JST),
        datetime(2026, 7, 31, 21, 30, tzinfo=JST),
    )
    assert {e.id for e in got} == {ind.id, sp.id}

    got_ind = store.events_between(
        datetime(2026, 7, 31, 0, 0, tzinfo=JST),
        datetime(2026, 8, 2, 0, 0, tzinfo=JST),
        kind=KIND_INDICATOR,
    )
    assert {e.id for e in got_ind} == {ind.id, outside.id}


def test_sent_log(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    now = datetime(2026, 7, 31, 9, 0, tzinfo=JST)
    assert store.was_sent("abc", "digest") is False
    store.mark_sent("abc", "digest", now)
    assert store.was_sent("abc", "digest") is True
    assert store.was_sent("abc", "pre_indicator") is False
    # 二重mark_sentは例外にならない
    store.mark_sent("abc", "digest", now)


def test_seen_news(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    now = datetime(2026, 7, 31, 9, 0, tzinfo=JST)
    assert store.seen_count() == 0
    assert store.is_seen("374772") is False
    store.mark_seen("374772", now)
    assert store.is_seen("374772") is True
    assert store.seen_count() == 1
    store.mark_seen("374772", now)  # 二重登録OK
    assert store.seen_count() == 1
