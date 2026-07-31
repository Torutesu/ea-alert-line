from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta

from ea_alert.config import Config, load_config
from ea_alert.db import Store
from ea_alert.fetchers import http
from ea_alert.fetchers.minkabu_schedule import (
    SCHEDULE_TITLE,
    parse_schedule_article,
)
from ea_alert.fetchers.minkabu_statement import (
    STATEMENT_LIST_URL,
    parse_statement_list,
)
from ea_alert.filters import indicator_matches
from ea_alert.models import JST, KIND_INDICATOR, KIND_SPEECH
from ea_alert.notifier import (
    LineNotifier,
    format_pre_indicators,
    format_pre_speech,
    format_statements,
)

logger = logging.getLogger(__name__)

STALE_STATEMENT = timedelta(hours=6)  # これより古い記事は速報しない


def _send_pre_alerts(config: Config, store: Store, notifier, now: datetime) -> None:
    # B: 経済指標の直前アラート（同時刻をグループ化して1通に、無料枠保護）
    window_end = now + timedelta(minutes=config.pre_indicator_minutes)
    # 対象イベントを先に収集し、datetime_jst でグループ化
    groups: dict[datetime, list] = {}
    for e in store.events_between(now, window_end, kind=KIND_INDICATOR):
        if not e.time_known:
            continue
        if not indicator_matches(e, config.currencies, config.pre_indicator_min_importance):
            continue
        if store.was_sent(e.id, "pre_indicator"):
            continue
        groups.setdefault(e.datetime_jst, []).append(e)
    # グループごとに1 broadcast → グループ内全イベントを mark_sent
    for group_events in groups.values():
        if config.notices.get("pre_indicator", True):
            notifier.broadcast(
                format_pre_indicators(group_events, config.pre_indicator_minutes)
            )
        for e in group_events:
            # 通知offでも送信済みにする: onに戻した際、過去窓のイベントをまとめて再通知しないため
            store.mark_sent(e.id, "pre_indicator", now)

    # C: 要人発言の予告
    window_end = now + timedelta(minutes=config.pre_speech_minutes)
    for e in store.events_between(now, window_end, kind=KIND_SPEECH):
        if store.was_sent(e.id, "pre_speech"):
            continue
        if config.notices.get("pre_speech", True):
            notifier.broadcast(format_pre_speech(e, config.pre_speech_minutes))
        # 通知offでも送信済みにする: onに戻した際、過去窓のイベントをまとめて再通知しないため
        store.mark_sent(e.id, "pre_speech", now)


def _poll_statements(config: Config, store: Store, notifier, http_get, now: datetime) -> None:
    html = http_get(STATEMENT_LIST_URL)
    items = parse_statement_list(html, today=now.date())
    if not items:
        # sent_log を流用して同日の2回目以降の重複通知を防ぐ（月200通無料枠保護）
        alert_id = f"parse_alert:minkabu:{now:%Y-%m-%d}"
        if not store.was_sent(alert_id, "admin"):
            notifier.notify_admin(
                "みんかぶstatement一覧のパース結果が0件です。サイト構造変更の可能性があります。"
            )
            store.mark_sent(alert_id, "admin", now)
        return
    bootstrap = store.seen_count() == 0  # 初回はまとめて既読化（過去分を連投しない）

    # 速報は個別送信せずに集めてから1通にまとめる（会見中の連投と課金通数を抑制）
    to_notify = []
    for item in items:
        if store.is_seen(item.news_id):
            continue
        if SCHEDULE_TITLE in item.title:
            # 発言予定記事: 本文を取得して speech イベントを upsert（速報通知はしない）
            article_html = http_get(item.url)
            store.upsert_events(
                parse_schedule_article(article_html, source_url=item.url)
            )
        elif (
            not bootstrap
            and config.notices.get("statement", True)
            and now - item.datetime_jst <= STALE_STATEMENT
        ):
            to_notify.append(item)
        store.mark_seen(item.news_id, now)

    if to_notify:
        notifier.broadcast(format_statements(to_notify))


def run(config: Config, store: Store, notifier, http_get, now: datetime) -> None:
    _send_pre_alerts(config, store, notifier, now)
    _poll_statements(config, store, notifier, http_get, now)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    config = load_config(args.config)
    store = Store(config.db_path)
    notifier = LineNotifier(config.line_token, config.admin_user_id)
    try:
        run(config, store, notifier, http.get, datetime.now(JST))
    finally:
        store.close()


if __name__ == "__main__":
    main()
