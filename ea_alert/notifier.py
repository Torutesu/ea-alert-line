from __future__ import annotations

import logging
import time
from datetime import date

import requests

from ea_alert.models import Event, StatementNews

logger = logging.getLogger(__name__)

BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"
PUSH_URL = "https://api.line.me/v2/bot/message/push"

_WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]


def _stars(importance: int) -> str:
    return "★" * importance


def _time_label(event: Event) -> str:
    return event.datetime_jst.strftime("%H:%M") if event.time_known else "時刻未定"


def _indicator_line(event: Event) -> str:
    line = f"{_time_label(event)} {event.country} {_stars(event.importance)} {event.title}"
    if event.forecast or event.previous:
        line += f"（予想 {event.forecast or '-'} / 前回 {event.previous or '-'}）"
    return line


def format_digest(events: list[Event], target_date: date) -> str:
    header = (
        f"☀️ 今日の経済指標 "
        f"{target_date.month}/{target_date.day}（{_WEEKDAYS[target_date.weekday()]}）"
    )
    # 時刻未定 → 時刻順
    ordered = sorted(events, key=lambda e: (e.time_known, e.datetime_jst))
    return "\n".join([header] + [_indicator_line(e) for e in ordered])


def format_pre_indicator(event: Event, minutes: int) -> str:
    return f"⚠️ まもなく発表（{minutes}分後）\n{_indicator_line(event)}"


def format_pre_speech(event: Event, minutes: int) -> str:
    if minutes % 60 == 0:
        lead = f"{minutes // 60}時間後"
    else:
        lead = f"{minutes}分後"
    return (
        f"🗣️ {lead}に要人発言・イベント\n"
        f"{event.datetime_jst:%H:%M} {event.title}"
    )


def format_statement(news: StatementNews) -> str:
    return f"🚨【速報】要人発言\n{news.title}\n▶ {news.url}"


class LineNotifier:
    def __init__(self, token: str, admin_user_id: str = "") -> None:
        self.token = token
        self.admin_user_id = admin_user_id

    def _post(self, url: str, payload: dict, retries: int = 3) -> None:
        for attempt in range(retries):
            try:
                resp = requests.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=15,
                )
                resp.raise_for_status()
                return
            except requests.RequestException:
                if attempt == retries - 1:
                    raise
                time.sleep(2**attempt)

    def broadcast(self, text: str) -> None:
        self._post(BROADCAST_URL, {"messages": [{"type": "text", "text": text}]})

    def push(self, to: str, text: str) -> None:
        self._post(
            PUSH_URL,
            {"to": to, "messages": [{"type": "text", "text": text}]},
        )

    def notify_admin(self, text: str) -> None:
        """運用警告。admin_user_id 未設定ならログ出力のみ。"""
        if self.admin_user_id:
            self.push(self.admin_user_id, f"🔧 [ea-alert-line] {text}")
        else:
            logger.warning("admin notice (no admin_user_id): %s", text)
