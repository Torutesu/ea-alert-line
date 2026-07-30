from __future__ import annotations

import re
from datetime import date, datetime

from bs4 import BeautifulSoup

from ea_alert.fetchers.gaikaex import resolve_year
from ea_alert.models import JST, StatementNews

BASE_URL = "https://fx.minkabu.jp"
STATEMENT_LIST_URL = BASE_URL + "/news?category=statement"

_HREF_RE = re.compile(r"^/news/(\d+)$")
_DT_RE = re.compile(r"(\d{1,2})/(\d{1,2})\([^)]+\)\s*(\d{1,2}):(\d{2})")


def parse_statement_list(html: str, today: date) -> list[StatementNews]:
    """statement一覧ページから要人発言カテゴリのニュースを抽出する。

    サイドバーの新着ニュース（株式・為替等）は span.fc-newscategory の
    カテゴリ名が「要人発言」でないため除外される。
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[StatementNews] = []
    for a in soup.select("li.list-link__item > a[href]"):
        m = _HREF_RE.match(a.get("href", ""))
        if m is None:
            continue
        category_el = a.select_one("span.fc-newscategory")
        if category_el is None or category_el.get_text(strip=True) != "要人発言":
            continue
        title_el = a.select_one("p.fbd")
        time_el = a.select_one("span.fc-sub")
        if title_el is None or time_el is None:
            continue
        dm = _DT_RE.search(time_el.get_text(strip=True))
        if dm is None:
            continue
        month, day, hour, minute = (int(g) for g in dm.groups())
        year = resolve_year(month, today)
        items.append(
            StatementNews(
                news_id=m.group(1),
                title=title_el.get_text(strip=True),
                datetime_jst=datetime(year, month, day, hour, minute, tzinfo=JST),
                url=BASE_URL + a["href"],
            )
        )
    return items
