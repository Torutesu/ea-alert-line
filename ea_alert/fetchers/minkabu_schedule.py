from __future__ import annotations

import re
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

from ea_alert.models import JST, KIND_SPEECH, Event

SCHEDULE_TITLE = "これからの予定【発言・イベント】"

_PUBLISHED_RE = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})\([^)]+\)\s*(\d{1,2}):(\d{2})")
_LINE_RE = re.compile(r"^(\d{1,2}):(\d{2})[\s　]+(.+)$")


def _parse_published(soup: BeautifulSoup) -> datetime | None:
    time_el = soup.select_one("article header time")
    if time_el is None:
        return None
    m = _PUBLISHED_RE.search(time_el.get_text(strip=True))
    if m is None:
        return None
    year, month, day, hour, minute = (int(g) for g in m.groups())
    return datetime(year, month, day, hour, minute, tzinfo=JST)


def parse_schedule_article(html: str, source_url: str) -> list[Event]:
    """「これからの予定【発言・イベント】」記事本文から時刻付き予定を抽出する。

    時刻なしの行（終日イベント・企業決算リスト等）は2時間前通知の対象外なので捨てる。
    行の時刻が配信時刻より前なら翌日の予定とみなす（深夜帯の米イベント対応）。
    """
    soup = BeautifulSoup(html, "html.parser")
    published = _parse_published(soup)
    body = soup.select_one("article p.news__text")
    if body is None or published is None:
        return []

    events: list[Event] = []
    for raw_line in body.get_text("\n").split("\n"):
        m = _LINE_RE.match(raw_line.strip())
        if m is None:
            continue
        hour, minute = int(m.group(1)), int(m.group(2))
        title = m.group(3).strip()
        dt = published.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if dt < published:
            dt += timedelta(days=1)
        events.append(
            Event(
                kind=KIND_SPEECH,
                datetime_jst=dt,
                time_known=True,
                country="",
                title=title,
                importance=3,
                source_url=source_url,
            )
        )
    return events
