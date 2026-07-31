from datetime import datetime
from pathlib import Path

from ea_alert.db import Store
from ea_alert.fetchers.minkabu_statement import STATEMENT_LIST_URL
from ea_alert.jobs import tick
from ea_alert.models import JST, KIND_INDICATOR, KIND_SPEECH, Event
from tests.fakes import FakeHttp, FakeNotifier
from tests.test_jobs_fetch_daily import make_config

FIXTURES = Path(__file__).parent / "fixtures"
LIST_HTML = (FIXTURES / "minkabu_statement_list.html").read_text(encoding="utf-8")
ARTICLE_HTML = (FIXTURES / "minkabu_schedule_article.html").read_text(encoding="utf-8")
EMPTY_LIST_HTML = "<html><body><ul></ul></body></html>"


def make_indicator(minutes_ahead, now, importance=3, country="米国", title="米GDP"):
    from datetime import timedelta
    return Event(
        kind=KIND_INDICATOR,
        datetime_jst=now + timedelta(minutes=minutes_ahead),
        time_known=True,
        country=country,
        title=title,
        importance=importance,
    )


def make_speech(minutes_ahead, now, title="パウエルFRB議長発言"):
    from datetime import timedelta
    return Event(
        kind=KIND_SPEECH,
        datetime_jst=now + timedelta(minutes=minutes_ahead),
        time_known=True,
        country="",
        title=title,
        importance=3,
    )


def setup(tmp_path, list_html=EMPTY_LIST_HTML, article_urls=None):
    config = make_config(tmp_path)
    store = Store(config.db_path)
    notifier = FakeNotifier()
    responses = {STATEMENT_LIST_URL: list_html}
    responses.update(article_urls or {})
    return config, store, notifier, FakeHttp(responses)


def test_pre_indicator_alert_fires_within_window(tmp_path):
    now = datetime(2026, 7, 31, 21, 5, tzinfo=JST)
    config, store, notifier, http_get = setup(tmp_path)
    store.upsert_events([
        make_indicator(25, now),                             # 25分後 → 対象
        make_indicator(45, now, title="45分後の指標"),        # 窓の外
        make_indicator(25, now, importance=2, title="★★指標"),  # 重要度不足
    ])

    tick.run(config, store, notifier, http_get, now)

    assert len(notifier.broadcasts) == 1
    assert "米GDP" in notifier.broadcasts[0]


def test_pre_indicator_alert_is_idempotent(tmp_path):
    now = datetime(2026, 7, 31, 21, 5, tzinfo=JST)
    config, store, notifier, http_get = setup(tmp_path)
    store.upsert_events([make_indicator(25, now)])

    tick.run(config, store, notifier, http_get, now)
    tick.run(config, store, notifier, http_get, now)

    assert len(notifier.broadcasts) == 1


def test_pre_speech_alert_fires_within_two_hours(tmp_path):
    now = datetime(2026, 7, 31, 19, 5, tzinfo=JST)
    config, store, notifier, http_get = setup(tmp_path)
    store.upsert_events([
        make_speech(115, now),                        # 115分後 → 対象
        make_speech(150, now, title="150分後の発言"),  # 窓の外
    ])

    tick.run(config, store, notifier, http_get, now)

    assert len(notifier.broadcasts) == 1
    assert "パウエルFRB議長発言" in notifier.broadcasts[0]


def test_statement_bootstrap_marks_seen_without_notify(tmp_path):
    # 初回実行（seen_newsが空）は既存記事を通知せず既読化だけする
    now = datetime(2026, 7, 30, 23, 50, tzinfo=JST)
    config, store, notifier, http_get = setup(
        tmp_path, list_html=LIST_HTML,
        article_urls={"https://fx.minkabu.jp/news/374708": ARTICLE_HTML},
    )

    tick.run(config, store, notifier, http_get, now)

    assert notifier.broadcasts == []
    assert store.seen_count() > 0
    # ブートストラップでも予定記事のパースは行われ、speechイベントが入る
    speeches = store.events_between(
        datetime(2026, 7, 30, 0, 0, tzinfo=JST),
        datetime(2026, 8, 1, 0, 0, tzinfo=JST),
        kind=KIND_SPEECH,
    )
    assert any("ベイリー英中銀総裁" in e.title for e in speeches)


def test_statement_new_items_notified_after_bootstrap(tmp_path):
    now = datetime(2026, 7, 30, 23, 50, tzinfo=JST)
    config, store, notifier, http_get = setup(
        tmp_path, list_html=LIST_HTML,
        article_urls={"https://fx.minkabu.jp/news/374708": ARTICLE_HTML},
    )
    # 1回目（ブートストラップ）
    tick.run(config, store, notifier, http_get, now)
    # 2回目: 374772だけ未読に戻して新着を装う
    store.conn.execute("DELETE FROM seen_news WHERE news_id = '374772'")
    store.conn.commit()

    tick.run(config, store, notifier, http_get, now)

    assert len(notifier.broadcasts) == 1
    assert "ベイリー英中銀総裁" in notifier.broadcasts[0]
    assert "これからの予定" not in notifier.broadcasts[0]


def test_stale_statement_not_notified(tmp_path):
    # 6時間より古い記事は（未読でも）速報しない
    now = datetime(2026, 7, 31, 12, 0, tzinfo=JST)  # 記事は 7/30 夜 → 12時間以上前
    config, store, notifier, http_get = setup(
        tmp_path, list_html=LIST_HTML,
        article_urls={"https://fx.minkabu.jp/news/374708": ARTICLE_HTML},
    )
    tick.run(config, store, notifier, http_get, now)          # bootstrap
    store.conn.execute("DELETE FROM seen_news WHERE news_id = '374772'")
    store.conn.commit()

    tick.run(config, store, notifier, http_get, now)

    assert notifier.broadcasts == []
    assert store.is_seen("374772")


def test_parse_error_admin_notice_fires_once_per_day(tmp_path):
    # 空一覧で tick.run を同日2回実行 → 管理者通知は1回のみ
    now = datetime(2026, 7, 31, 10, 0, tzinfo=JST)
    config, store, notifier, http_get = setup(tmp_path, list_html=EMPTY_LIST_HTML)

    tick.run(config, store, notifier, http_get, now)
    tick.run(config, store, notifier, http_get, now)

    assert len(notifier.admin_notices) == 1


def test_same_time_indicators_merged_into_one_broadcast(tmp_path):
    # 同時刻の★★★指標2件 → 1通にまとめる
    now = datetime(2026, 7, 31, 21, 5, tzinfo=JST)
    config, store, notifier, http_get = setup(tmp_path)
    e1 = make_indicator(25, now, title="米GDP")
    e2 = make_indicator(25, now, title="米PCE")
    store.upsert_events([e1, e2])

    tick.run(config, store, notifier, http_get, now)

    assert len(notifier.broadcasts) == 1
    assert "米GDP" in notifier.broadcasts[0]
    assert "米PCE" in notifier.broadcasts[0]


def test_same_time_indicators_idempotent_after_merge(tmp_path):
    # まとめ通知の後、2回目実行で増えない
    now = datetime(2026, 7, 31, 21, 5, tzinfo=JST)
    config, store, notifier, http_get = setup(tmp_path)
    store.upsert_events([
        make_indicator(25, now, title="米GDP"),
        make_indicator(25, now, title="米PCE"),
    ])

    tick.run(config, store, notifier, http_get, now)
    tick.run(config, store, notifier, http_get, now)

    assert len(notifier.broadcasts) == 1


def test_multiple_new_statements_merged_into_one_broadcast(tmp_path):
    """会見中の連続速報が1通にまとまること（連投・課金通数の抑制）。"""
    now = datetime(2026, 7, 30, 23, 50, tzinfo=JST)
    config, store, notifier, http_get = setup(
        tmp_path, list_html=LIST_HTML,
        article_urls={"https://fx.minkabu.jp/news/374708": ARTICLE_HTML},
    )
    tick.run(config, store, notifier, http_get, now)  # bootstrap
    # 複数の速報を未読に戻して「会見中に一気に配信された」状況を作る
    store.conn.execute(
        "DELETE FROM seen_news WHERE news_id IN ('374772','374771','374770')"
    )
    store.conn.commit()

    tick.run(config, store, notifier, http_get, now)

    assert len(notifier.broadcasts) == 1  # 3件でも1通
    text = notifier.broadcasts[0]
    assert "3件" in text
    assert text.count("🚨") == 1
    assert "374772" in text and "374771" in text and "374770" in text
    # 全件が既読化され、再実行しても増えない
    tick.run(config, store, notifier, http_get, now)
    assert len(notifier.broadcasts) == 1
