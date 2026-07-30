from datetime import datetime

from ea_alert.models import JST, KIND_INDICATOR, KIND_SPEECH, Event, StatementNews


def make_event(**overrides):
    defaults = dict(
        kind=KIND_INDICATOR,
        datetime_jst=datetime(2026, 7, 31, 21, 30, tzinfo=JST),
        time_known=True,
        country="米国",
        title="4-6月期GDP速報値",
        importance=3,
    )
    defaults.update(overrides)
    return Event(**defaults)


def test_event_id_is_stable():
    assert make_event().id == make_event().id


def test_event_id_changes_with_title():
    assert make_event().id != make_event(title="消費者物価指数").id


def test_event_id_distinguishes_time_unknown():
    # 同日同題でも「時刻未定」と「00:00発表」は別イベント
    known = make_event(datetime_jst=datetime(2026, 7, 31, 0, 0, tzinfo=JST))
    unknown = make_event(
        datetime_jst=datetime(2026, 7, 31, 0, 0, tzinfo=JST), time_known=False
    )
    assert known.id != unknown.id


def test_speech_event_defaults():
    e = Event(
        kind=KIND_SPEECH,
        datetime_jst=datetime(2026, 7, 31, 21, 0, tzinfo=JST),
        time_known=True,
        country="",
        title="ベイリー英中銀総裁、記者会見",
        importance=3,
    )
    assert e.forecast is None
    assert e.previous is None


def test_statement_news():
    n = StatementNews(
        news_id="374772",
        title="ベイリー英中銀総裁　CPIが我々の予想を下回っていることは心強い",
        datetime_jst=datetime(2026, 7, 30, 21, 30, tzinfo=JST),
        url="https://fx.minkabu.jp/news/374772",
    )
    assert n.news_id == "374772"
