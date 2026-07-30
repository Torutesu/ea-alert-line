from datetime import datetime
from pathlib import Path

from ea_alert.fetchers.minkabu_schedule import SCHEDULE_TITLE, parse_schedule_article
from ea_alert.models import JST, KIND_SPEECH

FIXTURE = Path(__file__).parent / "fixtures" / "minkabu_schedule_article.html"


def test_schedule_title_constant():
    assert SCHEDULE_TITLE == "これからの予定【発言・イベント】"


def test_parse_article_extracts_timed_speeches():
    html = FIXTURE.read_text(encoding="utf-8")
    events = parse_schedule_article(html, source_url="https://fx.minkabu.jp/news/374708")

    # フィクスチャ本文の時刻付き行は「21:00　ベイリー英中銀総裁、記者会見」のみ。
    # 「日銀金融政策決定会合（1日目、31日まで）」等の時刻なし行は対象外。
    assert len(events) == 1
    e = events[0]
    assert e.kind == KIND_SPEECH
    assert e.title == "ベイリー英中銀総裁、記者会見"
    assert e.country == ""
    assert e.importance == 3
    assert e.time_known is True
    # 配信 2026/07/30 15:28 より後の 21:00 → 同日
    assert e.datetime_jst == datetime(2026, 7, 30, 21, 0, tzinfo=JST)
    assert e.source_url == "https://fx.minkabu.jp/news/374708"


def test_time_before_publish_rolls_to_next_day():
    # 15:28配信の記事に「03:00」があれば翌日扱い（深夜の米イベント想定）
    html = FIXTURE.read_text(encoding="utf-8")
    html = html.replace(
        "21:00　ベイリー英中銀総裁、記者会見",
        "03:00　FOMC結果発表、パウエルFRB議長会見",
    )
    events = parse_schedule_article(html, source_url="")
    assert len(events) == 1
    assert events[0].datetime_jst == datetime(2026, 7, 31, 3, 0, tzinfo=JST)


def test_returns_empty_when_body_missing():
    assert parse_schedule_article("<html><body></body></html>", source_url="") == []
