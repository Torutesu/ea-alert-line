# EA危険通知LINE 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 経済指標・要人発言をスクレイピングし、EAが危険な時間帯の前にLINEへ通知するボット（毎朝ダイジェスト／指標30分前／発言予定2時間前／発言速報）を作る。

**Architecture:** cron起動の3ジョブ（fetch_daily / send_digest / tick）が、Fetchers（gaikaex・みんかぶのHTMLパーサ）→ Filter → SQLite（events / sent_log / seen_news）→ LINE Messaging API broadcast の層を通す。常駐プロセスなし。全時刻は JST（zoneinfo）。

**Tech Stack:** Python 3.11+, requests, beautifulsoup4, PyYAML, sqlite3（標準）, pytest。仕様書: `docs/superpowers/specs/2026-07-31-ea-alert-line-design.md`

**前提知識（スペックから引き写し・実HTML確認済みの事実）:**
- gaikaex カレンダーは SP向けマークアップ `ul.date_section` > `li.date_title`（`7/30（木）`）+ `li.data_box` が最もパースしやすい。`div.data_category` 内の `<p>` 3つが順に「国旗+国名（img alt）」「時刻 `08:50` or `--:--`」「`重要度★★`」。イベント名は `p.index_name`。予想/結果/前回は `div.data_result` 内の `div.statusWrap` 3つ（値なしは `*`）
- 国名 alt は14種: 日本/米国/ユーロ/イギリス/ドイツ/フランス/オーストラリア/ニュージーランド/カナダ/中国/トルコ/メキシコ/南アフリカ/香港
- みんかぶ statement 一覧は `li.list-link__item > a[href=/news/{id}]`、見出し `p.fbd`、カテゴリ `span.fc-newscategory`（サイドバー記事除外に使う）、日時 `span.fc-sub`（`07/30(木) 21:30`）
- みんかぶ「これからの予定【発言・イベント】」記事の本文は `<article>` 内 `<p class="news__text">` に `<br/>` 区切り。`21:00　ベイリー英中銀総裁、記者会見` 形式の行が時刻付き予定。配信日時は `article header time`（`2026/07/30(木) 15:28`）
- テストフィクスチャは取得済み: `tests/fixtures/gaikaex_calendar.html`（2026-07-30時点、7/30セクションに「日銀・金融政策決定会合(1日目)」★★・`--:--`、「前週分対外対内証券売買契約等の状況(対外中長期債)」★・08:50 を含む）、`tests/fixtures/minkabu_statement_list.html`（news_id 374772「ベイリー英中銀総裁　CPIが…」07/30 21:30、および 374738「これからの予定【発言・イベント】」を含む）、`tests/fixtures/minkabu_schedule_article.html`（news_id 374708、配信 2026/07/30 15:28、本文行「21:00　ベイリー英中銀総裁、記者会見」を含む）

**ファイル構成（最終形）:**

```
ea-alert-line/
├── config.yaml               # 設定（トークンは環境変数参照）
├── requirements.txt
├── conftest.py               # 空ファイル（pytestがリポジトリrootをsys.pathに足すため）
├── ea_alert/
│   ├── __init__.py
│   ├── models.py             # Event / StatementNews / JST定数
│   ├── config.py             # config.yaml 読み込み
│   ├── db.py                 # Store（SQLite: events / sent_log / seen_news）
│   ├── filters.py            # 国→通貨マッピングと指標フィルタ
│   ├── notifier.py           # メッセージ整形 + LINE Messaging API
│   ├── fetchers/
│   │   ├── __init__.py
│   │   ├── http.py           # UA付きGET・リトライ
│   │   ├── gaikaex.py        # 経済指標カレンダーパーサ
│   │   ├── minkabu_statement.py  # 発言速報一覧パーサ
│   │   └── minkabu_schedule.py   # 発言予定記事パーサ
│   └── jobs/
│       ├── __init__.py
│       ├── fetch_daily.py    # 毎日06:00
│       ├── send_digest.py    # 毎日09:00
│       └── tick.py           # 5分ごと
├── tests/
│   ├── fixtures/             # 済み（コミット済みHTML3点）
│   └── test_*.py
└── README.md                 # セットアップ・cron設定・LINE準備手順
```

---

### Task 1: プロジェクトスキャフォールド

**Files:**
- Create: `requirements.txt`
- Create: `conftest.py`
- Create: `ea_alert/__init__.py`
- Create: `ea_alert/fetchers/__init__.py`
- Create: `ea_alert/jobs/__init__.py`
- Create: `.gitignore`

- [ ] **Step 1: ファイルを作成**

`requirements.txt`:
```
requests>=2.31
beautifulsoup4>=4.12
PyYAML>=6.0
pytest>=8.0
```

`conftest.py`（空ファイル。pytest がリポジトリ root を `sys.path` に追加し `import ea_alert` を通すために置く）:
```python
```

`ea_alert/__init__.py`, `ea_alert/fetchers/__init__.py`, `ea_alert/jobs/__init__.py`（すべて空ファイル）

`.gitignore`:
```
__pycache__/
*.pyc
.venv/
data/
logs/
.pytest_cache/
```

- [ ] **Step 2: venv作成・依存インストール・pytest起動確認**

Run:
```bash
cd /Users/torutano/ea-alert-line && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt && .venv/bin/pytest --collect-only -q
```
Expected: `no tests ran`（エラーなしで終了すること）

- [ ] **Step 3: Commit**

```bash
git add requirements.txt conftest.py ea_alert .gitignore
git commit -m "chore: プロジェクトスキャフォールド"
```

---

### Task 2: models.py — 共通イベントモデル

**Files:**
- Create: `ea_alert/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_models.py`:
```python
from datetime import datetime

from ea_alert.models import JST, KIND_INDICATOR, KIND_SPEECH, Event, StatementNews


def make_event(**overrides):
    defaults = dict(
        kind=KIND_INDICATOR,
        datetime_jst=datetime(2026, 7, 31, 21, 30, tzinfo=JST),
        time_known=True,
        country="米国",
        title="4-6月期GDP速報値",
        importance=3,
    )
    defaults.update(overrides)
    return Event(**defaults)


def test_event_id_is_stable():
    assert make_event().id == make_event().id


def test_event_id_changes_with_title():
    assert make_event().id != make_event(title="消費者物価指数").id


def test_event_id_distinguishes_time_unknown():
    # 同日同題でも「時刻未定」と「00:00発表」は別イベント
    known = make_event(datetime_jst=datetime(2026, 7, 31, 0, 0, tzinfo=JST))
    unknown = make_event(
        datetime_jst=datetime(2026, 7, 31, 0, 0, tzinfo=JST), time_known=False
    )
    assert known.id != unknown.id


def test_speech_event_defaults():
    e = Event(
        kind=KIND_SPEECH,
        datetime_jst=datetime(2026, 7, 31, 21, 0, tzinfo=JST),
        time_known=True,
        country="",
        title="ベイリー英中銀総裁、記者会見",
        importance=3,
    )
    assert e.forecast is None
    assert e.previous is None


def test_statement_news():
    n = StatementNews(
        news_id="374772",
        title="ベイリー英中銀総裁　CPIが我々の予想を下回っていることは心強い",
        datetime_jst=datetime(2026, 7, 30, 21, 30, tzinfo=JST),
        url="https://fx.minkabu.jp/news/374772",
    )
    assert n.news_id == "374772"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_models.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'ea_alert.models'`）

- [ ] **Step 3: 実装**

`ea_alert/models.py`:
```python
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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_models.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add ea_alert/models.py tests/test_models.py
git commit -m "feat: 共通イベントモデル（Event / StatementNews）"
```

---

### Task 3: config.py — 設定読み込み

**Files:**
- Create: `ea_alert/config.py`
- Create: `config.yaml`
- Test: `tests/test_config.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_config.py`:
```python
import textwrap

from ea_alert.config import load_config

SAMPLE = textwrap.dedent(
    """
    currencies: [USD, JPY, EUR, GBP]
    digest_min_importance: 2
    pre_indicator_min_importance: 3
    pre_indicator_minutes: 30
    pre_speech_minutes: 120
    notices:
      digest: true
      pre_indicator: true
      pre_speech: true
      statement: true
    line:
      channel_access_token_env: LINE_CHANNEL_ACCESS_TOKEN
      admin_user_id: "U123"
    db_path: data/ea_alert.db
    """
)


def test_load_config(tmp_path, monkeypatch):
    p = tmp_path / "config.yaml"
    p.write_text(SAMPLE, encoding="utf-8")
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "token-abc")

    cfg = load_config(str(p))

    assert cfg.currencies == ["USD", "JPY", "EUR", "GBP"]
    assert cfg.digest_min_importance == 2
    assert cfg.pre_indicator_min_importance == 3
    assert cfg.pre_indicator_minutes == 30
    assert cfg.pre_speech_minutes == 120
    assert cfg.notices["statement"] is True
    assert cfg.line_token == "token-abc"
    assert cfg.admin_user_id == "U123"
    assert cfg.db_path == "data/ea_alert.db"


def test_load_config_without_env(tmp_path, monkeypatch):
    p = tmp_path / "config.yaml"
    p.write_text(SAMPLE, encoding="utf-8")
    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)

    cfg = load_config(str(p))

    assert cfg.line_token == ""
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 実装**

`ea_alert/config.py`:
```python
from __future__ import annotations

import os
from dataclasses import dataclass

import yaml


@dataclass(frozen=True)
class Config:
    currencies: list[str]
    digest_min_importance: int
    pre_indicator_min_importance: int
    pre_indicator_minutes: int
    pre_speech_minutes: int
    notices: dict[str, bool]
    line_token: str
    admin_user_id: str
    db_path: str


def load_config(path: str) -> Config:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    line = raw["line"]
    return Config(
        currencies=list(raw["currencies"]),
        digest_min_importance=int(raw["digest_min_importance"]),
        pre_indicator_min_importance=int(raw["pre_indicator_min_importance"]),
        pre_indicator_minutes=int(raw["pre_indicator_minutes"]),
        pre_speech_minutes=int(raw["pre_speech_minutes"]),
        notices=dict(raw["notices"]),
        line_token=os.environ.get(line["channel_access_token_env"], ""),
        admin_user_id=str(line.get("admin_user_id", "") or ""),
        db_path=str(raw["db_path"]),
    )
```

`config.yaml`（本番用のデフォルト。トークンは環境変数で渡すためコミット可）:
```yaml
currencies: [USD, JPY, EUR, GBP]
digest_min_importance: 2        # 朝ダイジェスト: ★★以上
pre_indicator_min_importance: 3 # 直前アラート: ★★★のみ
pre_indicator_minutes: 30       # 指標の何分前に通知するか
pre_speech_minutes: 120         # 発言予定の何分前に通知するか
notices:
  digest: true
  pre_indicator: true
  pre_speech: true
  statement: true
line:
  channel_access_token_env: LINE_CHANNEL_ACCESS_TOKEN
  admin_user_id: ""             # 管理者のLINE userId（空なら管理者通知はログのみ）
db_path: data/ea_alert.db
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add ea_alert/config.py config.yaml tests/test_config.py
git commit -m "feat: 設定読み込み（config.yaml + 環境変数トークン）"
```

---

### Task 4: db.py — SQLite ストア

**Files:**
- Create: `ea_alert/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_db.py`:
```python
from datetime import datetime

from ea_alert.db import Store
from ea_alert.models import JST, KIND_INDICATOR, KIND_SPEECH, Event


def make_event(**overrides):
    defaults = dict(
        kind=KIND_INDICATOR,
        datetime_jst=datetime(2026, 7, 31, 21, 30, tzinfo=JST),
        time_known=True,
        country="米国",
        title="4-6月期GDP速報値",
        importance=3,
        forecast="2.0%",
        previous="1.4%",
        source_url="https://example.com",
    )
    defaults.update(overrides)
    return Event(**defaults)


def test_upsert_and_roundtrip(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    e = make_event()
    store.upsert_events([e])
    got = store.events_between(
        datetime(2026, 7, 31, 0, 0, tzinfo=JST),
        datetime(2026, 7, 31, 23, 59, tzinfo=JST),
    )
    assert got == [e]


def test_upsert_is_idempotent(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    e = make_event()
    store.upsert_events([e])
    store.upsert_events([e])
    got = store.events_between(
        datetime(2026, 7, 31, 0, 0, tzinfo=JST),
        datetime(2026, 7, 31, 23, 59, tzinfo=JST),
    )
    assert len(got) == 1


def test_events_between_bounds_inclusive_and_kind_filter(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    ind = make_event()
    sp = make_event(
        kind=KIND_SPEECH, country="", title="会見",
        datetime_jst=datetime(2026, 7, 31, 21, 30, tzinfo=JST),
    )
    outside = make_event(title="翌日分", datetime_jst=datetime(2026, 8, 1, 9, 0, tzinfo=JST))
    store.upsert_events([ind, sp, outside])

    # 境界ちょうど（21:30〜21:30）は両端含む
    got = store.events_between(
        datetime(2026, 7, 31, 21, 30, tzinfo=JST),
        datetime(2026, 7, 31, 21, 30, tzinfo=JST),
    )
    assert {e.id for e in got} == {ind.id, sp.id}

    got_ind = store.events_between(
        datetime(2026, 7, 31, 0, 0, tzinfo=JST),
        datetime(2026, 8, 2, 0, 0, tzinfo=JST),
        kind=KIND_INDICATOR,
    )
    assert {e.id for e in got_ind} == {ind.id, outside.id}


def test_sent_log(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    now = datetime(2026, 7, 31, 9, 0, tzinfo=JST)
    assert store.was_sent("abc", "digest") is False
    store.mark_sent("abc", "digest", now)
    assert store.was_sent("abc", "digest") is True
    assert store.was_sent("abc", "pre_indicator") is False
    # 二重mark_sentは例外にならない
    store.mark_sent("abc", "digest", now)


def test_seen_news(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    now = datetime(2026, 7, 31, 9, 0, tzinfo=JST)
    assert store.seen_count() == 0
    assert store.is_seen("374772") is False
    store.mark_seen("374772", now)
    assert store.is_seen("374772") is True
    assert store.seen_count() == 1
    store.mark_seen("374772", now)  # 二重登録OK
    assert store.seen_count() == 1
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_db.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 実装**

`ea_alert/db.py`:
```python
from __future__ import annotations

import os
import sqlite3
from datetime import datetime

from ea_alert.models import Event

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  datetime_jst TEXT NOT NULL,
  time_known INTEGER NOT NULL DEFAULT 1,
  country TEXT NOT NULL,
  title TEXT NOT NULL,
  importance INTEGER NOT NULL,
  forecast TEXT,
  previous TEXT,
  source_url TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS sent_log (
  event_id TEXT NOT NULL,
  notice_type TEXT NOT NULL,
  sent_at TEXT NOT NULL,
  PRIMARY KEY (event_id, notice_type)
);
CREATE TABLE IF NOT EXISTS seen_news (
  news_id TEXT PRIMARY KEY,
  seen_at TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str) -> None:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(_SCHEMA)

    def upsert_events(self, events: list[Event]) -> None:
        rows = [
            (
                e.id, e.kind, e.datetime_jst.isoformat(), int(e.time_known),
                e.country, e.title, e.importance, e.forecast, e.previous, e.source_url,
            )
            for e in events
        ]
        self.conn.executemany(
            """INSERT INTO events
               (id, kind, datetime_jst, time_known, country, title,
                importance, forecast, previous, source_url)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 forecast=excluded.forecast,
                 previous=excluded.previous""",
            rows,
        )
        self.conn.commit()

    def events_between(
        self, start: datetime, end: datetime, kind: str | None = None
    ) -> list[Event]:
        sql = (
            "SELECT kind, datetime_jst, time_known, country, title,"
            " importance, forecast, previous, source_url"
            " FROM events WHERE datetime_jst >= ? AND datetime_jst <= ?"
        )
        params: list[str] = [start.isoformat(), end.isoformat()]
        if kind is not None:
            sql += " AND kind = ?"
            params.append(kind)
        sql += " ORDER BY datetime_jst"
        rows = self.conn.execute(sql, params).fetchall()
        return [
            Event(
                kind=r[0],
                datetime_jst=datetime.fromisoformat(r[1]),
                time_known=bool(r[2]),
                country=r[3],
                title=r[4],
                importance=r[5],
                forecast=r[6],
                previous=r[7],
                source_url=r[8],
            )
            for r in rows
        ]

    def was_sent(self, event_id: str, notice_type: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sent_log WHERE event_id = ? AND notice_type = ?",
            (event_id, notice_type),
        ).fetchone()
        return row is not None

    def mark_sent(self, event_id: str, notice_type: str, now: datetime) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO sent_log (event_id, notice_type, sent_at) VALUES (?,?,?)",
            (event_id, notice_type, now.isoformat()),
        )
        self.conn.commit()

    def is_seen(self, news_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM seen_news WHERE news_id = ?", (news_id,)
        ).fetchone()
        return row is not None

    def mark_seen(self, news_id: str, now: datetime) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO seen_news (news_id, seen_at) VALUES (?,?)",
            (news_id, now.isoformat()),
        )
        self.conn.commit()

    def seen_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM seen_news").fetchone()[0]

    def close(self) -> None:
        self.conn.close()
```

注意: `events_between` は ISO8601 文字列の辞書順比較で範囲判定する。JST固定で `+09:00` サフィックスが揃うため辞書順＝時刻順が成立する。

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_db.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add ea_alert/db.py tests/test_db.py
git commit -m "feat: SQLiteストア（events / sent_log / seen_news）"
```

---

### Task 5: fetchers/http.py — UA付きGET・リトライ

**Files:**
- Create: `ea_alert/fetchers/http.py`
- Test: `tests/test_http.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_http.py`:
```python
import pytest
import requests

from ea_alert.fetchers import http


class FakeResponse:
    def __init__(self, text="ok", status=200):
        self.text = text
        self.status_code = status
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


def test_get_success(monkeypatch):
    def fake_get(url, headers, timeout):
        assert "ea-alert-line" in headers["User-Agent"]
        return FakeResponse("hello")

    monkeypatch.setattr(http.requests, "get", fake_get)
    assert http.get("https://example.com") == "hello"


def test_get_retries_then_succeeds(monkeypatch):
    calls = []

    def flaky_get(url, headers, timeout):
        calls.append(url)
        if len(calls) < 3:
            raise requests.ConnectionError("boom")
        return FakeResponse("recovered")

    monkeypatch.setattr(http.requests, "get", flaky_get)
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    assert http.get("https://example.com") == "recovered"
    assert len(calls) == 3


def test_get_raises_after_all_retries(monkeypatch):
    def always_fail(url, headers, timeout):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(http.requests, "get", always_fail)
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    with pytest.raises(requests.ConnectionError):
        http.get("https://example.com")
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_http.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 実装**

`ea_alert/fetchers/http.py`:
```python
from __future__ import annotations

import time

import requests

USER_AGENT = "ea-alert-line/1.0 (personal notification bot)"


def get(url: str, *, retries: int = 3, timeout: int = 15) -> str:
    """UA明示・指数バックオフ付きGET。最終試行も失敗したら例外を投げ直す。"""
    for attempt in range(retries):
        try:
            resp = requests.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=timeout
            )
            resp.raise_for_status()
            if resp.apparent_encoding:
                resp.encoding = resp.apparent_encoding
            return resp.text
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_http.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add ea_alert/fetchers/http.py tests/test_http.py
git commit -m "feat: UA付きHTTP GET（リトライ・指数バックオフ）"
```

---

### Task 6: fetchers/gaikaex.py — 経済指標カレンダーパーサ

**Files:**
- Create: `ea_alert/fetchers/gaikaex.py`
- Test: `tests/test_gaikaex.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_gaikaex.py`:
```python
from datetime import date, datetime
from pathlib import Path

from ea_alert.fetchers.gaikaex import parse_calendar, resolve_year
from ea_alert.models import JST, KIND_INDICATOR

FIXTURE = Path(__file__).parent / "fixtures" / "gaikaex_calendar.html"


def load_events():
    html = FIXTURE.read_text(encoding="utf-8")
    return parse_calendar(html, today=date(2026, 7, 30))


def test_parse_returns_events():
    events = load_events()
    assert len(events) > 50  # フィクスチャは1週間分・100件超のはず
    assert all(e.kind == KIND_INDICATOR for e in events)


def test_boj_meeting_time_unknown():
    events = load_events()
    boj = [e for e in events if e.title == "日銀・金融政策決定会合(1日目)"]
    assert len(boj) == 1
    e = boj[0]
    assert e.country == "日本"
    assert e.importance == 2
    assert e.time_known is False
    assert e.datetime_jst == datetime(2026, 7, 30, 0, 0, tzinfo=JST)


def test_timed_indicator():
    events = load_events()
    sec = [
        e for e in events
        if e.title == "前週分対外対内証券売買契約等の状況(対外中長期債)"
        and e.datetime_jst.date() == date(2026, 7, 30)
    ]
    assert len(sec) == 1
    e = sec[0]
    assert e.country == "日本"
    assert e.importance == 1
    assert e.time_known is True
    assert e.datetime_jst == datetime(2026, 7, 30, 8, 50, tzinfo=JST)


def test_all_countries_known():
    # flag alt が全て想定14か国のいずれかであること（新国追加の検知を兼ねる）
    known = {
        "日本", "米国", "ユーロ", "イギリス", "ドイツ", "フランス",
        "オーストラリア", "ニュージーランド", "カナダ", "中国",
        "トルコ", "メキシコ", "南アフリカ", "香港",
    }
    events = load_events()
    assert {e.country for e in events} <= known


def test_resolve_year_rollover():
    assert resolve_year(1, date(2026, 12, 30)) == 2027   # 年末に1月の予定
    assert resolve_year(12, date(2027, 1, 2)) == 2026    # 年始に12月の実績
    assert resolve_year(7, date(2026, 7, 30)) == 2026
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_gaikaex.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 実装**

`ea_alert/fetchers/gaikaex.py`:
```python
from __future__ import annotations

import re
from datetime import date, datetime

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
                dt = datetime(year, month, day, int(tm.group(1)), int(tm.group(2)), tzinfo=JST)
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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_gaikaex.py -v`
Expected: 5 passed

失敗した場合はフィクスチャ実物とセレクタのずれを疑い、`python3 -c` で `tests/fixtures/gaikaex_calendar.html` の該当box周辺を確認してからパーサ側を直す（テストの期待値はスペック確認済みの事実なので変えない）。

- [ ] **Step 5: Commit**

```bash
git add ea_alert/fetchers/gaikaex.py tests/test_gaikaex.py
git commit -m "feat: gaikaex経済指標カレンダーパーサ"
```

---

### Task 7: fetchers/minkabu_statement.py — 発言速報一覧パーサ

**Files:**
- Create: `ea_alert/fetchers/minkabu_statement.py`
- Test: `tests/test_minkabu_statement.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_minkabu_statement.py`:
```python
from datetime import date, datetime
from pathlib import Path

from ea_alert.fetchers.minkabu_statement import parse_statement_list
from ea_alert.models import JST

FIXTURE = Path(__file__).parent / "fixtures" / "minkabu_statement_list.html"


def load_items():
    html = FIXTURE.read_text(encoding="utf-8")
    return parse_statement_list(html, today=date(2026, 7, 30))


def test_parse_returns_statement_items():
    items = load_items()
    assert len(items) >= 10
    ids = {i.news_id for i in items}
    assert "374772" in ids


def test_item_fields():
    items = load_items()
    bailey = next(i for i in items if i.news_id == "374772")
    assert "ベイリー英中銀総裁" in bailey.title
    assert bailey.datetime_jst == datetime(2026, 7, 30, 21, 30, tzinfo=JST)
    assert bailey.url == "https://fx.minkabu.jp/news/374772"


def test_includes_schedule_article():
    # 「これからの予定【発言・イベント】」記事も一覧に含まれる（除外はジョブ側で行う）
    items = load_items()
    assert any("これからの予定【発言・イベント】" in i.title for i in items)


def test_only_statement_category():
    # サイドバー等の別カテゴリ記事（株式・為替）が混入しないこと
    html = FIXTURE.read_text(encoding="utf-8")
    items = parse_statement_list(html, today=date(2026, 7, 30))
    assert all(i.title for i in items)
    # フィクスチャの statement 一覧は 07/30 の記事のみ
    assert all(i.datetime_jst.date() == date(2026, 7, 30) for i in items)
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_minkabu_statement.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 実装**

`ea_alert/fetchers/minkabu_statement.py`:
```python
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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_minkabu_statement.py -v`
Expected: 4 passed

失敗した場合（例: サイドバーに `fc-newscategory` が無く混入する等）はフィクスチャを `python3 -c` で確認しパーサ側を調整する。

- [ ] **Step 5: Commit**

```bash
git add ea_alert/fetchers/minkabu_statement.py tests/test_minkabu_statement.py
git commit -m "feat: みんかぶ要人発言速報一覧パーサ"
```

---

### Task 8: fetchers/minkabu_schedule.py — 発言予定記事パーサ

**Files:**
- Create: `ea_alert/fetchers/minkabu_schedule.py`
- Test: `tests/test_minkabu_schedule.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_minkabu_schedule.py`:
```python
from datetime import datetime
from pathlib import Path

from ea_alert.fetchers.minkabu_schedule import SCHEDULE_TITLE, parse_schedule_article
from ea_alert.models import JST, KIND_SPEECH

FIXTURE = Path(__file__).parent / "fixtures" / "minkabu_schedule_article.html"


def test_schedule_title_constant():
    assert SCHEDULE_TITLE == "これからの予定【発言・イベント】"


def test_parse_article_extracts_timed_speeches():
    html = FIXTURE.read_text(encoding="utf-8")
    events = parse_schedule_article(html, source_url="https://fx.minkabu.jp/news/374708")

    # フィクスチャ本文の時刻付き行は「21:00　ベイリー英中銀総裁、記者会見」のみ。
    # 「日銀金融政策決定会合（1日目、31日まで）」等の時刻なし行は対象外。
    assert len(events) == 1
    e = events[0]
    assert e.kind == KIND_SPEECH
    assert e.title == "ベイリー英中銀総裁、記者会見"
    assert e.country == ""
    assert e.importance == 3
    assert e.time_known is True
    # 配信 2026/07/30 15:28 より後の 21:00 → 同日
    assert e.datetime_jst == datetime(2026, 7, 30, 21, 0, tzinfo=JST)
    assert e.source_url == "https://fx.minkabu.jp/news/374708"


def test_time_before_publish_rolls_to_next_day():
    # 15:28配信の記事に「03:00」があれば翌日扱い（深夜の米イベント想定）
    html = FIXTURE.read_text(encoding="utf-8")
    html = html.replace(
        "21:00　ベイリー英中銀総裁、記者会見",
        "03:00　FOMC結果発表、パウエルFRB議長会見",
    )
    events = parse_schedule_article(html, source_url="")
    assert len(events) == 1
    assert events[0].datetime_jst == datetime(2026, 7, 31, 3, 0, tzinfo=JST)


def test_returns_empty_when_body_missing():
    assert parse_schedule_article("<html><body></body></html>", source_url="") == []
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_minkabu_schedule.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 実装**

`ea_alert/fetchers/minkabu_schedule.py`:
```python
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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_minkabu_schedule.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add ea_alert/fetchers/minkabu_schedule.py tests/test_minkabu_schedule.py
git commit -m "feat: みんかぶ発言予定記事パーサ（翌日繰り上げ対応）"
```

---

### Task 9: filters.py — 通貨・重要度フィルタ

**Files:**
- Create: `ea_alert/filters.py`
- Test: `tests/test_filters.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_filters.py`:
```python
from datetime import datetime

from ea_alert.filters import COUNTRY_TO_CURRENCY, indicator_matches
from ea_alert.models import JST, KIND_INDICATOR, Event


def make_event(country="米国", importance=3):
    return Event(
        kind=KIND_INDICATOR,
        datetime_jst=datetime(2026, 7, 31, 21, 30, tzinfo=JST),
        time_known=True,
        country=country,
        title="テスト指標",
        importance=importance,
    )


CURRENCIES = ["USD", "JPY", "EUR", "GBP"]


def test_mapping_covers_gaikaex_countries():
    assert COUNTRY_TO_CURRENCY["米国"] == "USD"
    assert COUNTRY_TO_CURRENCY["日本"] == "JPY"
    assert COUNTRY_TO_CURRENCY["ユーロ"] == "EUR"
    assert COUNTRY_TO_CURRENCY["ドイツ"] == "EUR"
    assert COUNTRY_TO_CURRENCY["フランス"] == "EUR"
    assert COUNTRY_TO_CURRENCY["イギリス"] == "GBP"


def test_matches_target_currency_and_importance():
    assert indicator_matches(make_event("米国", 3), CURRENCIES, min_importance=2)
    assert indicator_matches(make_event("ドイツ", 2), CURRENCIES, min_importance=2)


def test_rejects_low_importance():
    assert not indicator_matches(make_event("米国", 1), CURRENCIES, min_importance=2)


def test_rejects_non_target_country():
    assert not indicator_matches(make_event("トルコ", 3), CURRENCIES, min_importance=2)
    assert not indicator_matches(make_event("南アフリカ", 3), CURRENCIES, min_importance=2)


def test_rejects_unknown_country():
    assert not indicator_matches(make_event("未知の国", 3), CURRENCIES, min_importance=2)
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_filters.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 実装**

`ea_alert/filters.py`:
```python
from __future__ import annotations

from ea_alert.models import Event

# gaikaex カレンダーの flag alt（14か国）→ 通貨コード
COUNTRY_TO_CURRENCY = {
    "日本": "JPY",
    "米国": "USD",
    "ユーロ": "EUR",
    "ドイツ": "EUR",
    "フランス": "EUR",
    "イギリス": "GBP",
    "オーストラリア": "AUD",
    "ニュージーランド": "NZD",
    "カナダ": "CAD",
    "中国": "CNY",
    "トルコ": "TRY",
    "メキシコ": "MXN",
    "南アフリカ": "ZAR",
    "香港": "HKD",
}


def indicator_matches(
    event: Event, currencies: list[str], min_importance: int
) -> bool:
    """経済指標が通知対象か判定する。要人発言（speech/statement）には適用しない。"""
    if event.importance < min_importance:
        return False
    currency = COUNTRY_TO_CURRENCY.get(event.country)
    return currency in currencies
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_filters.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add ea_alert/filters.py tests/test_filters.py
git commit -m "feat: 通貨・重要度フィルタ"
```

---

### Task 10: notifier.py — メッセージ整形 + LINE送信

**Files:**
- Create: `ea_alert/notifier.py`
- Test: `tests/test_notifier.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_notifier.py`:
```python
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
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_notifier.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 実装**

`ea_alert/notifier.py`:
```python
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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_notifier.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add ea_alert/notifier.py tests/test_notifier.py
git commit -m "feat: メッセージ整形とLINE Messaging API送信"
```

---

### Task 11: jobs/fetch_daily.py — 毎朝6時の取得ジョブ

**Files:**
- Create: `ea_alert/jobs/fetch_daily.py`
- Test: `tests/test_jobs_fetch_daily.py`

テスト用フェイク（このタスクで作成し、以降のジョブテストでも同じものを使う）:

- Create: `tests/fakes.py`

- [ ] **Step 1: フェイクと失敗するテストを書く**

`tests/fakes.py`:
```python
"""ジョブテスト共用のフェイク。"""


class FakeNotifier:
    def __init__(self):
        self.broadcasts = []
        self.admin_notices = []

    def broadcast(self, text):
        self.broadcasts.append(text)

    def push(self, to, text):
        raise AssertionError("ジョブはpushを直接呼ばない")

    def notify_admin(self, text):
        self.admin_notices.append(text)


class FakeHttp:
    """URL→レスポンス本文の辞書を返すフェイクGET。"""

    def __init__(self, responses):
        self.responses = responses
        self.requested = []

    def __call__(self, url, **kwargs):
        self.requested.append(url)
        return self.responses[url]
```

`tests/test_jobs_fetch_daily.py`:
```python
from datetime import datetime
from pathlib import Path

from ea_alert.config import Config
from ea_alert.db import Store
from ea_alert.fetchers.gaikaex import CALENDAR_URL
from ea_alert.jobs import fetch_daily
from ea_alert.models import JST, KIND_INDICATOR
from tests.fakes import FakeHttp, FakeNotifier

FIXTURE = Path(__file__).parent / "fixtures" / "gaikaex_calendar.html"


def make_config(tmp_path):
    return Config(
        currencies=["USD", "JPY", "EUR", "GBP"],
        digest_min_importance=2,
        pre_indicator_min_importance=3,
        pre_indicator_minutes=30,
        pre_speech_minutes=120,
        notices={"digest": True, "pre_indicator": True, "pre_speech": True, "statement": True},
        line_token="t",
        admin_user_id="U1",
        db_path=str(tmp_path / "t.db"),
    )


def test_fetch_daily_stores_today_and_tomorrow(tmp_path):
    config = make_config(tmp_path)
    store = Store(config.db_path)
    notifier = FakeNotifier()
    http_get = FakeHttp({CALENDAR_URL: FIXTURE.read_text(encoding="utf-8")})
    now = datetime(2026, 7, 30, 6, 0, tzinfo=JST)

    fetch_daily.run(config, store, notifier, http_get, now)

    today_events = store.events_between(
        datetime(2026, 7, 30, 0, 0, tzinfo=JST),
        datetime(2026, 7, 30, 23, 59, tzinfo=JST),
        kind=KIND_INDICATOR,
    )
    tomorrow_events = store.events_between(
        datetime(2026, 7, 31, 0, 0, tzinfo=JST),
        datetime(2026, 7, 31, 23, 59, tzinfo=JST),
        kind=KIND_INDICATOR,
    )
    assert len(today_events) > 0
    assert len(tomorrow_events) > 0
    # 2日より先は保存しない
    later = store.events_between(
        datetime(2026, 8, 1, 0, 0, tzinfo=JST),
        datetime(2026, 12, 31, 0, 0, tzinfo=JST),
    )
    assert later == []
    assert notifier.admin_notices == []


def test_fetch_daily_alerts_admin_on_empty_parse(tmp_path):
    config = make_config(tmp_path)
    store = Store(config.db_path)
    notifier = FakeNotifier()
    http_get = FakeHttp({CALENDAR_URL: "<html><body>改修されました</body></html>"})
    now = datetime(2026, 7, 30, 6, 0, tzinfo=JST)

    fetch_daily.run(config, store, notifier, http_get, now)

    assert len(notifier.admin_notices) == 1
    assert "0件" in notifier.admin_notices[0]
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_jobs_fetch_daily.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 実装**

`ea_alert/jobs/fetch_daily.py`:
```python
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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_jobs_fetch_daily.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add ea_alert/jobs/fetch_daily.py tests/fakes.py tests/test_jobs_fetch_daily.py
git commit -m "feat: fetch_dailyジョブ（当日+翌日をupsert、0件で管理者警告）"
```

---

### Task 12: jobs/send_digest.py — 毎朝9時のダイジェスト

**Files:**
- Create: `ea_alert/jobs/send_digest.py`
- Test: `tests/test_jobs_send_digest.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_jobs_send_digest.py`:
```python
from datetime import datetime

from ea_alert.db import Store
from ea_alert.jobs import send_digest
from ea_alert.models import JST, KIND_INDICATOR, Event
from tests.fakes import FakeNotifier
from tests.test_jobs_fetch_daily import make_config


def make_indicator(title, importance=3, country="米国", hour=21, minute=30, day=31):
    return Event(
        kind=KIND_INDICATOR,
        datetime_jst=datetime(2026, 7, day, hour, minute, tzinfo=JST),
        time_known=True,
        country=country,
        title=title,
        importance=importance,
    )


def test_digest_sends_filtered_events(tmp_path):
    config = make_config(tmp_path)
    store = Store(config.db_path)
    notifier = FakeNotifier()
    store.upsert_events([
        make_indicator("米GDP", importance=3),
        make_indicator("トルコCPI", importance=3, country="トルコ"),  # 対象外通貨
        make_indicator("低重要度", importance=1),                      # 重要度不足
        make_indicator("別日分", day=1),  # 7/1 → 当日(7/31)ではない
    ])
    now = datetime(2026, 7, 31, 9, 0, tzinfo=JST)

    send_digest.run(config, store, notifier, now)

    assert len(notifier.broadcasts) == 1
    text = notifier.broadcasts[0]
    assert "米GDP" in text
    assert "トルコCPI" not in text
    assert "低重要度" not in text
    assert "別日分" not in text


def test_digest_is_idempotent(tmp_path):
    config = make_config(tmp_path)
    store = Store(config.db_path)
    notifier = FakeNotifier()
    store.upsert_events([make_indicator("米GDP")])
    now = datetime(2026, 7, 31, 9, 0, tzinfo=JST)

    send_digest.run(config, store, notifier, now)
    send_digest.run(config, store, notifier, now)  # 再実行しても送らない

    assert len(notifier.broadcasts) == 1


def test_digest_skips_when_no_events(tmp_path):
    config = make_config(tmp_path)
    store = Store(config.db_path)
    notifier = FakeNotifier()
    now = datetime(2026, 7, 31, 9, 0, tzinfo=JST)

    send_digest.run(config, store, notifier, now)

    assert notifier.broadcasts == []


def test_digest_respects_notices_flag(tmp_path):
    config = make_config(tmp_path)
    config.notices["digest"] = False
    store = Store(config.db_path)
    notifier = FakeNotifier()
    store.upsert_events([make_indicator("米GDP")])
    now = datetime(2026, 7, 31, 9, 0, tzinfo=JST)

    send_digest.run(config, store, notifier, now)

    assert notifier.broadcasts == []
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_jobs_send_digest.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 実装**

`ea_alert/jobs/send_digest.py`:
```python
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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_jobs_send_digest.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add ea_alert/jobs/send_digest.py tests/test_jobs_send_digest.py
git commit -m "feat: send_digestジョブ（当日ダイジェスト・冪等）"
```

---

### Task 13: jobs/tick.py — 5分ごとの直前通知・速報ジョブ

**Files:**
- Create: `ea_alert/jobs/tick.py`
- Test: `tests/test_jobs_tick.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_jobs_tick.py`:
```python
from datetime import datetime
from pathlib import Path

from ea_alert.db import Store
from ea_alert.fetchers.minkabu_statement import STATEMENT_LIST_URL
from ea_alert.jobs import tick
from ea_alert.models import JST, KIND_INDICATOR, KIND_SPEECH, Event
from tests.fakes import FakeHttp, FakeNotifier
from tests.test_jobs_fetch_daily import make_config

FIXTURES = Path(__file__).parent / "fixtures"
LIST_HTML = (FIXTURES / "minkabu_statement_list.html").read_text(encoding="utf-8")
ARTICLE_HTML = (FIXTURES / "minkabu_schedule_article.html").read_text(encoding="utf-8")
EMPTY_LIST_HTML = "<html><body><ul></ul></body></html>"


def make_indicator(minutes_ahead, now, importance=3, country="米国", title="米GDP"):
    from datetime import timedelta
    return Event(
        kind=KIND_INDICATOR,
        datetime_jst=now + timedelta(minutes=minutes_ahead),
        time_known=True,
        country=country,
        title=title,
        importance=importance,
    )


def make_speech(minutes_ahead, now, title="パウエルFRB議長発言"):
    from datetime import timedelta
    return Event(
        kind=KIND_SPEECH,
        datetime_jst=now + timedelta(minutes=minutes_ahead),
        time_known=True,
        country="",
        title=title,
        importance=3,
    )


def setup(tmp_path, list_html=EMPTY_LIST_HTML, article_urls=None):
    config = make_config(tmp_path)
    store = Store(config.db_path)
    notifier = FakeNotifier()
    responses = {STATEMENT_LIST_URL: list_html}
    responses.update(article_urls or {})
    return config, store, notifier, FakeHttp(responses)


def test_pre_indicator_alert_fires_within_window(tmp_path):
    now = datetime(2026, 7, 31, 21, 5, tzinfo=JST)
    config, store, notifier, http_get = setup(tmp_path)
    store.upsert_events([
        make_indicator(25, now),                             # 25分後 → 対象
        make_indicator(45, now, title="45分後の指標"),        # 窓の外
        make_indicator(25, now, importance=2, title="★★指標"),  # 重要度不足
    ])

    tick.run(config, store, notifier, http_get, now)

    assert len(notifier.broadcasts) == 1
    assert "米GDP" in notifier.broadcasts[0]


def test_pre_indicator_alert_is_idempotent(tmp_path):
    now = datetime(2026, 7, 31, 21, 5, tzinfo=JST)
    config, store, notifier, http_get = setup(tmp_path)
    store.upsert_events([make_indicator(25, now)])

    tick.run(config, store, notifier, http_get, now)
    tick.run(config, store, notifier, http_get, now)

    assert len(notifier.broadcasts) == 1


def test_pre_speech_alert_fires_within_two_hours(tmp_path):
    now = datetime(2026, 7, 31, 19, 5, tzinfo=JST)
    config, store, notifier, http_get = setup(tmp_path)
    store.upsert_events([
        make_speech(115, now),                        # 115分後 → 対象
        make_speech(150, now, title="150分後の発言"),  # 窓の外
    ])

    tick.run(config, store, notifier, http_get, now)

    assert len(notifier.broadcasts) == 1
    assert "パウエルFRB議長発言" in notifier.broadcasts[0]


def test_statement_bootstrap_marks_seen_without_notify(tmp_path):
    # 初回実行（seen_newsが空）は既存記事を通知せず既読化だけする
    now = datetime(2026, 7, 30, 23, 50, tzinfo=JST)
    config, store, notifier, http_get = setup(
        tmp_path, list_html=LIST_HTML,
        article_urls={"https://fx.minkabu.jp/news/374738": ARTICLE_HTML},
    )

    tick.run(config, store, notifier, http_get, now)

    assert notifier.broadcasts == []
    assert store.seen_count() > 0
    # ブートストラップでも予定記事のパースは行われ、speechイベントが入る
    speeches = store.events_between(
        datetime(2026, 7, 30, 0, 0, tzinfo=JST),
        datetime(2026, 8, 1, 0, 0, tzinfo=JST),
        kind=KIND_SPEECH,
    )
    assert any("ベイリー英中銀総裁" in e.title for e in speeches)


def test_statement_new_items_notified_after_bootstrap(tmp_path):
    now = datetime(2026, 7, 30, 23, 50, tzinfo=JST)
    config, store, notifier, http_get = setup(
        tmp_path, list_html=LIST_HTML,
        article_urls={"https://fx.minkabu.jp/news/374738": ARTICLE_HTML},
    )
    # 1回目（ブートストラップ）
    tick.run(config, store, notifier, http_get, now)
    # 2回目: 374772だけ未読に戻して新着を装う
    store.conn.execute("DELETE FROM seen_news WHERE news_id = '374772'")
    store.conn.commit()

    tick.run(config, store, notifier, http_get, now)

    assert len(notifier.broadcasts) == 1
    assert "ベイリー英中銀総裁" in notifier.broadcasts[0]
    assert "これからの予定" not in notifier.broadcasts[0]


def test_stale_statement_not_notified(tmp_path):
    # 6時間より古い記事は（未読でも）速報しない
    now = datetime(2026, 7, 31, 12, 0, tzinfo=JST)  # 記事は 7/30 夜 → 12時間以上前
    config, store, notifier, http_get = setup(
        tmp_path, list_html=LIST_HTML,
        article_urls={"https://fx.minkabu.jp/news/374738": ARTICLE_HTML},
    )
    tick.run(config, store, notifier, http_get, now)          # bootstrap
    store.conn.execute("DELETE FROM seen_news WHERE news_id = '374772'")
    store.conn.commit()

    tick.run(config, store, notifier, http_get, now)

    assert notifier.broadcasts == []
    assert store.is_seen("374772")
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/pytest tests/test_jobs_tick.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 実装**

`ea_alert/jobs/tick.py`:
```python
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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/pytest tests/test_jobs_tick.py -v`
Expected: 6 passed

- [ ] **Step 5: 全テストを通しで実行**

Run: `.venv/bin/pytest -q`
Expected: 全テスト passed（50件前後）

- [ ] **Step 6: Commit**

```bash
git add ea_alert/jobs/tick.py tests/test_jobs_tick.py
git commit -m "feat: tickジョブ（直前通知・発言予告・速報・予定記事取り込み）"
```

---

### Task 14: README — セットアップ・LINE準備・cron設定

**Files:**
- Create: `README.md`

- [ ] **Step 1: README.md を書く**

`README.md`:
````markdown
# EA危険通知LINE (ea-alert-line)

FXの経済指標・要人発言をスクレイピングし、EA（自動売買）が危険な時間帯の前にLINEへ通知するボット。

## 通知の種類

| 種類 | タイミング |
|------|-----------|
| ☀️ 経済指標 朝ダイジェスト | 毎朝 9:00 |
| ⚠️ 経済指標 直前アラート | ★★★指標の発表30分前 |
| 🗣️ 要人発言 予告 | 発言予定の2時間前 |
| 🚨 要人発言 速報 | 発言ニュース検知後すぐ |

情報源: GMO外貨 経済指標カレンダー / みんかぶFX（発言予定・速報）。
詳細設計: `docs/superpowers/specs/2026-07-31-ea-alert-line-design.md`

## セットアップ

### 1. LINE公式アカウントの準備

1. [LINE Developers](https://developers.line.biz/) でプロバイダーと **Messaging API チャネル**を作成
2. チャネルの「Messaging API設定」から**チャネルアクセストークン（長期）**を発行
3. 利用者に公式アカウントのQRコードを共有し、友だち追加してもらう
4. （任意）管理者警告を受け取る場合は自分の userId を `config.yaml` の `admin_user_id` に設定
   （userId はチャネルの Webhook などで確認。未設定ならログ出力のみ）

※無料プランは月200通まで。通知種別は `config.yaml` の `notices` で個別にオフにできる。

### 2. VPSへの配置

```bash
git clone <このリポジトリ> && cd ea-alert-line
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export LINE_CHANNEL_ACCESS_TOKEN="（発行したトークン）"
mkdir -p data logs
```

動作確認（テスト実行）:

```bash
.venv/bin/pytest -q
```

手動でジョブを1回ずつ実行して疎通確認:

```bash
.venv/bin/python -m ea_alert.jobs.fetch_daily --config config.yaml
.venv/bin/python -m ea_alert.jobs.send_digest --config config.yaml
.venv/bin/python -m ea_alert.jobs.tick --config config.yaml
```

※ tick の初回実行はブートストラップとして既存ニュースを既読化するだけで通知しない。

### 3. cron設定

`crontab -e` で以下を登録（パスは環境に合わせる）。
**時刻はJST前提**。VPSのタイムゾーンがJST以外の場合は `CRON_TZ=Asia/Tokyo` を先頭に付ける。

```cron
CRON_TZ=Asia/Tokyo
LINE_CHANNEL_ACCESS_TOKEN=（発行したトークン）

0 6 * * *   cd /path/to/ea-alert-line && .venv/bin/python -m ea_alert.jobs.fetch_daily >> logs/fetch.log 2>&1
0 9 * * *   cd /path/to/ea-alert-line && .venv/bin/python -m ea_alert.jobs.send_digest >> logs/digest.log 2>&1
*/5 * * * * cd /path/to/ea-alert-line && .venv/bin/python -m ea_alert.jobs.tick >> logs/tick.log 2>&1
```

## 設定（config.yaml）

| キー | 意味 | デフォルト |
|------|------|-----------|
| `currencies` | 通知対象の通貨 | USD, JPY, EUR, GBP |
| `digest_min_importance` | ダイジェストの最低重要度（★の数） | 2 |
| `pre_indicator_min_importance` | 直前アラートの最低重要度 | 3 |
| `pre_indicator_minutes` | 指標の何分前に通知 | 30 |
| `pre_speech_minutes` | 発言予定の何分前に通知 | 120 |
| `notices.*` | 通知種別ごとのon/off | すべてtrue |

## 運用メモ

- パース結果が0件になったら管理者へ警告が飛ぶ（サイト構造変更のサイン）。
  `tests/fixtures/` のHTMLを取り直してテストを走らせ、パーサを修正する
- 速報は見出し＋出典リンクのみ（記事本文は転載しない）
- DB（`data/ea_alert.db`）を消すと次のtickがブートストラップ扱いになるだけで安全
````

- [ ] **Step 2: 全テスト通し + 手動スモーク（トークンなし）**

Run:
```bash
.venv/bin/pytest -q && .venv/bin/python -c "from ea_alert.jobs import fetch_daily, send_digest, tick; print('imports ok')"
```
Expected: 全テスト passed / `imports ok`

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README（セットアップ・LINE準備・cron設定）"
```

---

## 実装後の受け入れ確認（実運用前チェック）

1. VPS（またはローカル）で `LINE_CHANNEL_ACCESS_TOKEN` を設定し、`fetch_daily` → `send_digest` を手動実行して自分のLINEにダイジェストが届くこと
2. `tick` を2回実行し、1回目（ブートストラップ）は通知なし・2回目以降で新着発言だけが速報されること
3. gaikaex・みんかぶへのアクセス頻度が cron 設定どおり（日次1回＋5分毎）であること
