from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta

from ea_alert.config import Config, load_config
from ea_alert.db import Store
from ea_alert.fetchers import http
from ea_alert.fetchers.gaikaex import CALENDAR_URL, parse_calendar
from ea_alert.models import JST
from ea_alert.notifier import LineNotifier

logger = logging.getLogger(__name__)


def run(config: Config, store: Store, notifier, http_get, now: datetime) -> None:
    html = http_get(CALENDAR_URL)
    events = parse_calendar(html, today=now.date())
    if not events:
        notifier.notify_admin(
            "gaikaexカレンダーのパース結果が0件です。サイト構造変更の可能性があります。"
        )
        return
    today = now.date()
    window = [
        e for e in events
        if today <= e.datetime_jst.date() <= today + timedelta(days=1)
    ]
    store.upsert_events(window)
    logger.info("stored %d events (today+tomorrow)", len(window))


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
