from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup

from ea_alert.models import JST, KIND_INDICATOR, Event

CALENDAR_URL = "https://www.gaikaex.com/gaikaex/mark/calendar/"

_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})")
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")


def resolve_year(month: int, today: date) -> int:
    """月だけの表記から年を補完する（年末年始の跨ぎに対応）。"""
    if month < today.month - 6:
        return today.year + 1
    if month > today.month + 6:
        return today.year - 1
    return today.year


def _clean_value(text: str) -> str | None:
    """予想/結果/前回セルの値を取り出す。ラベルを除去し '*'（値なし）は None。"""
    for label in ("予想", "結果", "前回"):
        text = text.replace(label, "")
    text = text.strip()
    return text if text and text != "*" else None


def parse_calendar(html: str, today: date) -> list[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events: list[Event] = []
    for section in soup.select("ul.date_section"):
        title_li = section.select_one("li.date_title")
        if title_li is None:
            continue
        m = _DATE_RE.search(title_li.get_text(strip=True))
        if m is None:
            continue
        month, day = int(m.group(1)), int(m.group(2))
        year = resolve_year(month, today)

        for box in section.select("li.data_box"):
            category = box.select_one("div.data_category")
            name_el = box.select_one("p.index_name")
            if category is None or name_el is None:
                continue
            ps = category.find_all("p")
            if len(ps) < 3:
                continue
            flag_img = ps[0].find("img")
            country = flag_img["alt"] if flag_img else ""
            time_text = ps[1].get_text(strip=True)
            importance = ps[2].get_text(strip=True).count("★")

            tm = _TIME_RE.match(time_text)
            if tm:
                hour, minute = int(tm.group(1)), int(tm.group(2))
                if hour < 24:
                    # 通常時刻
                    dt = datetime(year, month, day, hour, minute, tzinfo=JST)
                else:
                    # FX業界慣習の24時間超表記（例: 28:00 = 翌日04:00 JST）
                    # timedelta に委ねることで月末・年末跨ぎを自動処理する
                    dt = datetime(year, month, day, 0, 0, tzinfo=JST) + timedelta(
                        days=1, hours=hour - 24, minutes=minute
                    )
                time_known = True
            else:
                dt = datetime(year, month, day, 0, 0, tzinfo=JST)
                time_known = False

            wraps = box.select("div.data_result div.statusWrap")
            forecast = _clean_value(wraps[0].get_text(strip=True)) if len(wraps) > 0 else None
            previous = _clean_value(wraps[2].get_text(strip=True)) if len(wraps) > 2 else None

            events.append(
                Event(
                    kind=KIND_INDICATOR,
                    datetime_jst=dt,
                    time_known=time_known,
                    country=country,
                    title=name_el.get_text(strip=True),
                    importance=importance,
                    forecast=forecast,
                    previous=previous,
                    source_url=CALENDAR_URL,
                )
            )
    return events
