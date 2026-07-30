from __future__ import annotations

import argparse
import logging
from datetime import datetime

from ea_alert.config import Config, load_config
from ea_alert.db import Store
from ea_alert.filters import indicator_matches
from ea_alert.models import JST, KIND_INDICATOR
from ea_alert.notifier import LineNotifier, format_digest

logger = logging.getLogger(__name__)


def run(config: Config, store: Store, notifier, now: datetime) -> None:
    digest_id = f"digest:{now:%Y-%m-%d}"
    if store.was_sent(digest_id, "digest"):
        return
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    events = store.events_between(day_start, day_end, kind=KIND_INDICATOR)
    targets = [
        e for e in events
        if indicator_matches(e, config.currencies, config.digest_min_importance)
    ]
    if not targets:
        logger.info("no digest targets for %s", now.date())
        return
    if not config.notices.get("digest", True):
        return
    notifier.broadcast(format_digest(targets, now.date()))
    store.mark_sent(digest_id, "digest", now)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    config = load_config(args.config)
    store = Store(config.db_path)
    notifier = LineNotifier(config.line_token, config.admin_user_id)
    try:
        run(config, store, notifier, datetime.now(JST))
    finally:
        store.close()


if __name__ == "__main__":
    main()
