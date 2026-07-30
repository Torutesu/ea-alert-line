from datetime import date, datetime
from pathlib import Path

from ea_alert.fetchers.minkabu_statement import parse_statement_list
from ea_alert.models import JST

FIXTURE = Path(__file__).parent / "fixtures" / "minkabu_statement_list.html"


def load_items():
    html = FIXTURE.read_text(encoding="utf-8")
    return parse_statement_list(html, today=date(2026, 7, 30))


def test_parse_returns_statement_items():
    items = load_items()
    assert len(items) >= 10
    ids = {i.news_id for i in items}
    assert "374772" in ids


def test_item_fields():
    items = load_items()
    bailey = next(i for i in items if i.news_id == "374772")
    assert "ベイリー英中銀総裁" in bailey.title
    assert bailey.datetime_jst == datetime(2026, 7, 30, 21, 30, tzinfo=JST)
    assert bailey.url == "https://fx.minkabu.jp/news/374772"


def test_includes_schedule_article():
    # 「これからの予定【発言・イベント】」記事も一覧に含まれる（除外はジョブ側で行う）
    items = load_items()
    assert any("これからの予定【発言・イベント】" in i.title for i in items)


def test_only_statement_category():
    # サイドバー等の別カテゴリ記事（株式・為替）が混入しないこと
    html = FIXTURE.read_text(encoding="utf-8")
    items = parse_statement_list(html, today=date(2026, 7, 30))
    assert all(i.title for i in items)
    # フィクスチャの statement 一覧は 07/30 の記事のみ
    assert all(i.datetime_jst.date() == date(2026, 7, 30) for i in items)
