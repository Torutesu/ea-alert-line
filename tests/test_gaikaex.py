from datetime import date, datetime
from pathlib import Path

from ea_alert.fetchers.gaikaex import parse_calendar, resolve_year
from ea_alert.models import JST, KIND_INDICATOR

FIXTURE = Path(__file__).parent / "fixtures" / "gaikaex_calendar.html"


def load_events():
    html = FIXTURE.read_text(encoding="utf-8")
    return parse_calendar(html, today=date(2026, 7, 30))


def test_parse_returns_events():
    events = load_events()
    assert len(events) > 50  # フィクスチャは1週間分・100件超のはず
    assert all(e.kind == KIND_INDICATOR for e in events)


def test_boj_meeting_time_unknown():
    events = load_events()
    boj = [e for e in events if e.title == "日銀・金融政策決定会合(1日目)"]
    assert len(boj) == 1
    e = boj[0]
    assert e.country == "日本"
    assert e.importance == 2
    assert e.time_known is False
    assert e.datetime_jst == datetime(2026, 7, 30, 0, 0, tzinfo=JST)


def test_timed_indicator():
    events = load_events()
    sec = [
        e for e in events
        if e.title == "前週分対外対内証券売買契約等の状況(対外中長期債)"
        and e.datetime_jst.date() == date(2026, 7, 30)
    ]
    assert len(sec) == 1
    e = sec[0]
    assert e.country == "日本"
    assert e.importance == 1
    assert e.time_known is True
    assert e.datetime_jst == datetime(2026, 7, 30, 8, 50, tzinfo=JST)


def test_all_countries_known():
    # flag alt が全て想定14か国のいずれかであること（新国追加の検知を兼ねる）
    known = {
        "日本", "米国", "ユーロ", "イギリス", "ドイツ", "フランス",
        "オーストラリア", "ニュージーランド", "カナダ", "中国",
        "トルコ", "メキシコ", "南アフリカ", "香港",
        "スイス",  # フィクスチャ実物に含まれる（仕様の14か国リストに未記載だが実在する）
    }
    events = load_events()
    assert {e.country for e in events} <= known


def test_resolve_year_rollover():
    assert resolve_year(1, date(2026, 12, 30)) == 2027   # 年末に1月の予定
    assert resolve_year(12, date(2027, 1, 2)) == 2026    # 年始に12月の実績
    assert resolve_year(7, date(2026, 7, 30)) == 2026


def test_24h_notation_pmi():
    # フィクスチャ: セクション 8/3（月） の「7月製造業購買担当者景気指数(PMI)」は 24:00 表記
    # → 翌日（8/4）の 00:00 JST、time_known=True
    events = load_events()
    pmi = [e for e in events if e.title == "7月製造業購買担当者景気指数(PMI)"]
    assert len(pmi) >= 1
    # 24:00 表記のもの（8/3セクション）
    entry = next(
        (e for e in pmi if e.datetime_jst == datetime(2026, 8, 4, 0, 0, tzinfo=JST)),
        None,
    )
    assert entry is not None, "24:00表記のPMIが8/4 00:00 JSTとしてパースされていない"
    assert entry.time_known is True


def test_28h_notation_mexico_central_bank():
    # フィクスチャ: セクション 8/6（木） の「メキシコ中銀、政策金利」は 28:00 表記
    # → 翌日（8/7）の 04:00 JST、time_known=True
    events = load_events()
    mexico = [e for e in events if e.title == "メキシコ中銀、政策金利"]
    assert len(mexico) == 1
    e = mexico[0]
    assert e.datetime_jst == datetime(2026, 8, 7, 4, 0, tzinfo=JST)
    assert e.time_known is True
