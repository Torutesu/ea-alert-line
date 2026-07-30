from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

KIND_INDICATOR = "indicator"  # 経済指標
KIND_SPEECH = "speech"        # 要人発言の予定


@dataclass(frozen=True)
class Event:
    """経済指標・発言予定を正規化した共通イベント。"""

    kind: str
    datetime_jst: datetime      # JST。時刻未定は当日00:00を入れ time_known=False にする
    time_known: bool
    country: str                # gaikaexのflag alt（例 "米国"）。speechは ""
    title: str
    importance: int             # 1〜3（★の数。speechは3固定）
    forecast: str | None = None
    previous: str | None = None
    source_url: str = ""

    @property
    def id(self) -> str:
        hm = self.datetime_jst.strftime("%H%M") if self.time_known else "----"
        raw = f"{self.kind}|{self.datetime_jst:%Y%m%d}|{hm}|{self.country}|{self.title}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class StatementNews:
    """みんかぶの要人発言速報（事後ニュース）1件。"""

    news_id: str
    title: str
    datetime_jst: datetime
    url: str
