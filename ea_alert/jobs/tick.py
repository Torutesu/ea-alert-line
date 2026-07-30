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
    format_pre_indicator,
    format_pre_speech,
    format_statement,
)

logger = logging.getLogger(__name__)

STALE_STATEMENT = timedelta(hours=6)  # これより古い記事は速報しない


def _send_pre_alerts(config: Config, store: Store, notifier, now: datetime) -> None:
    # B: 経済指標の直前アラート
    window_end = now + timedelta(minutes=config.pre_indicator_minutes)
    for e in store.events_between(now, window_end, kind=KIND_INDICATOR):
        if not e.time_known:
            continue
        if not indicator_matches(e, config.currencies, config.pre_indicator_min_importance):
            continue
        if store.was_sent(e.id, "pre_indicator"):
            continue
        if config.notices.get("pre_indicator", True):
            notifier.broadcast(
                format_pre_indicator(e, config.pre_indicator_minutes)
            )
        store.mark_sent(e.id, "pre_indicator", now)

    # C: 要人発言の予告
    window_end = now + timedelta(minutes=config.pre_speech_minutes)
    for e in store.events_between(now, window_end, kind=KIND_SPEECH):
        if store.was_sent(e.id, "pre_speech"):
            continue
        if config.notices.get("pre_speech", True):
            notifier.broadcast(format_pre_speech(e, config.pre_speech_minutes))
        store.mark_sent(e.id, "pre_speech", now)


def _poll_statements(config: Config, store: Store, notifier, http_get, now: datetime) -> None:
    html = http_get(STATEMENT_LIST_URL)
    items = parse_statement_list(html, today=now.date())
    if not items:
        notifier.notify_admin(
            "みんかぶstatement一覧のパース結果が0件です。サイト構造変更の可能性があります。"
        )
        return
    bootstrap = store.seen_count() == 0  # 初回はまとめて既読化（過去分を連投しない）

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
            notifier.broadcast(format_statement(item))
        store.mark_seen(item.news_id, now)


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
