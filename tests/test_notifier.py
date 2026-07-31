from datetime import date, datetime

from ea_alert import notifier
from ea_alert.models import JST, KIND_INDICATOR, KIND_SPEECH, Event, StatementNews


def make_indicator(**overrides):
    defaults = dict(
        kind=KIND_INDICATOR,
        datetime_jst=datetime(2026, 7, 31, 21, 30, tzinfo=JST),
        time_known=True,
        country="米国",
        title="4-6月期GDP速報値",
        importance=3,
        forecast="2.0%",
        previous="1.4%",
    )
    defaults.update(overrides)
    return Event(**defaults)


def test_format_digest():
    events = [
        make_indicator(),
        make_indicator(
            title="日銀・金融政策決定会合", country="日本", importance=2,
            datetime_jst=datetime(2026, 7, 31, 0, 0, tzinfo=JST),
            time_known=False, forecast=None, previous=None,
        ),
    ]
    text = notifier.format_digest(events, date(2026, 7, 31))
    assert "7/31（金）" in text
    assert "時刻未定 日本 ★★ 日銀・金融政策決定会合" in text
    assert "21:30 米国 ★★★ 4-6月期GDP速報値（予想 2.0% / 前回 1.4%）" in text
    # 時刻未定が先頭に来る
    assert text.index("時刻未定") < text.index("21:30")


def test_format_pre_indicator():
    text = notifier.format_pre_indicator(make_indicator(), minutes=30)
    assert "30分後" in text
    assert "21:30 米国 ★★★ 4-6月期GDP速報値" in text


def test_format_pre_speech():
    e = Event(
        kind=KIND_SPEECH,
        datetime_jst=datetime(2026, 7, 30, 21, 0, tzinfo=JST),
        time_known=True,
        country="",
        title="ベイリー英中銀総裁、記者会見",
        importance=3,
    )
    text = notifier.format_pre_speech(e, minutes=120)
    assert "2時間後" in text
    assert "21:00 ベイリー英中銀総裁、記者会見" in text


def test_format_statement():
    n = StatementNews(
        news_id="374772",
        title="ベイリー英中銀総裁　CPIが我々の予想を下回っていることは心強い",
        datetime_jst=datetime(2026, 7, 30, 21, 30, tzinfo=JST),
        url="https://fx.minkabu.jp/news/374772",
    )
    text = notifier.format_statement(n)
    assert "速報" in text
    assert "ベイリー英中銀総裁" in text
    assert "https://fx.minkabu.jp/news/374772" in text


def test_line_notifier_broadcast(monkeypatch):
    sent = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

    def fake_post(url, headers, json, timeout):
        sent["url"] = url
        sent["headers"] = headers
        sent["json"] = json
        return FakeResponse()

    monkeypatch.setattr(notifier.requests, "post", fake_post)
    ln = notifier.LineNotifier("token-abc", admin_user_id="U123")
    ln.broadcast("hello")

    assert sent["url"] == "https://api.line.me/v2/bot/message/broadcast"
    assert sent["headers"]["Authorization"] == "Bearer token-abc"
    assert sent["json"] == {"messages": [{"type": "text", "text": "hello"}]}


def test_line_notifier_notify_admin_push(monkeypatch):
    sent = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

    def fake_post(url, headers, json, timeout):
        sent["url"] = url
        sent["json"] = json
        return FakeResponse()

    monkeypatch.setattr(notifier.requests, "post", fake_post)
    ln = notifier.LineNotifier("token-abc", admin_user_id="U123")
    ln.notify_admin("パース0件")

    assert sent["url"] == "https://api.line.me/v2/bot/message/push"
    assert sent["json"]["to"] == "U123"


def test_line_notifier_notify_admin_without_user_id(monkeypatch):
    called = []
    monkeypatch.setattr(
        notifier.requests, "post", lambda *a, **k: called.append(1)
    )
    ln = notifier.LineNotifier("token-abc", admin_user_id="")
    ln.notify_admin("パース0件")  # userId未設定ならAPIを呼ばずログのみ
    assert called == []


def make_news(news_id, title, minute=30):
    return StatementNews(
        news_id=news_id,
        title=title,
        datetime_jst=datetime(2026, 7, 30, 21, minute, tzinfo=JST),
        url=f"https://fx.minkabu.jp/news/{news_id}",
    )


def test_format_statements_single_matches_singular_format():
    n = make_news("374772", "ベイリー英中銀総裁　CPIが我々の予想を下回っている")
    assert notifier.format_statements([n]) == notifier.format_statement(n)


def test_format_statements_merges_multiple_into_one_message():
    items = [
        make_news("3", "ベイリー英中銀総裁　利上げが必要になる可能性", minute=25),
        make_news("1", "ベイリー英中銀総裁　CPIは予想を下回る", minute=15),
        make_news("2", "ベイリー英中銀総裁　second round effects", minute=20),
    ]
    text = notifier.format_statements(items)

    assert text.count("🚨") == 1  # ヘッダーは1つだけ
    assert "3件" in text
    for n in items:
        assert n.title in text
        assert n.url in text
    # 時系列（古い順）に並ぶ
    assert text.index("CPIは予想を下回る") < text.index("second round effects") < text.index("利上げが必要になる可能性")
    # 時刻が各行に付く
    assert "21:15" in text and "21:20" in text and "21:25" in text
