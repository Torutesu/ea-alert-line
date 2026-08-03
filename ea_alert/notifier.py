from __future__ import annotations

import logging
import time
from datetime import date

import requests

from ea_alert.models import Event, StatementNews

logger = logging.getLogger(__name__)

BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"
PUSH_URL = "https://api.line.me/v2/bot/message/push"

# 再送で回復し得るのはサーバ側の一時障害だけ。4xx（429=通数上限/レート超過を含む）は
# 数秒後に送り直しても同じ結果になり、通数と実行時間を浪費するだけなので再送しない。
RETRIABLE_STATUS = {500, 502, 503, 504}
# 設定ミス（トークン不正・権限不足）は運用者が直すまで回復しないので握りつぶさない
FATAL_STATUS = {401, 403}

_WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]


class LineApiError(RuntimeError):
    """LINE Messaging API への送信失敗。status_code は接続失敗時のみ None。"""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    @property
    def is_fatal(self) -> bool:
        """設定ミス由来か（=握りつぶさずジョブを落とすべきか）。"""
        return self.status_code in FATAL_STATUS


def try_broadcast(notifier, text: str) -> bool:
    """送信失敗でジョブを落とさずに続行する（成功したら True）。

    tickは5分ごとに走るため、送信失敗で異常終了すると状態DBがコミットされず、
    次のtickが同じ通知を作り直して再送を繰り返す。通数上限（429）に当たった
    ときほどこの再送ループが効いてしまうので、失敗はログに残して先へ進める。
    """
    try:
        notifier.broadcast(text)
        return True
    except LineApiError as exc:
        if exc.is_fatal:
            raise
        logger.error("LINE送信に失敗、この通知はスキップします: %s", exc)
        return False


def _response_detail(resp) -> str:
    body = (getattr(resp, "text", "") or "").strip().replace("\n", " ")
    return body[:200] if body else "(本文なし)"


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


def format_pre_indicators(events: list[Event], minutes: int) -> str:
    """同時刻の複数指標を1通にまとめる（無料枠保護）。"""
    lines = [f"⚠️ まもなく発表（{minutes}分後）"]
    lines += [_indicator_line(e) for e in sorted(events, key=lambda e: e.datetime_jst)]
    return "\n".join(lines)


def format_pre_indicator(event: Event, minutes: int) -> str:
    return format_pre_indicators([event], minutes)


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


def format_statements(items: list[StatementNews]) -> str:
    """複数の速報を1通にまとめる。

    会見中は数分で何本もニュース化されるため、1件1通だと通知が連投され、
    LINEの課金通数も膨らむ。1回のポーリングで拾った分をまとめて1通にする。
    """
    if len(items) == 1:
        return format_statement(items[0])
    ordered = sorted(items, key=lambda n: n.datetime_jst)
    lines = [f"🚨【速報】要人発言 {len(ordered)}件"]
    for n in ordered:
        lines.append(f"\n{n.datetime_jst:%H:%M} {n.title}\n▶ {n.url}")
    return "\n".join(lines)


class LineNotifier:
    def __init__(self, token: str, admin_user_id: str = "") -> None:
        self.token = token
        self.admin_user_id = admin_user_id

    def _post(self, url: str, payload: dict, retries: int = 3) -> None:
        last_error: LineApiError | None = None
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
            except requests.RequestException as exc:
                last_error = LineApiError(f"{url} への接続に失敗: {exc}")
            else:
                if resp.status_code < 400:
                    return
                # 原因（通数上限か一時的なレート超過か等）はレスポンス本文にしか出ない
                last_error = LineApiError(
                    f"{url} が {resp.status_code} を返しました: {_response_detail(resp)}",
                    status_code=resp.status_code,
                )
                if resp.status_code not in RETRIABLE_STATUS:
                    raise last_error
            if attempt == retries - 1:
                raise last_error
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
        if not self.admin_user_id:
            logger.warning("admin notice (no admin_user_id): %s", text)
            return
        try:
            self.push(self.admin_user_id, f"🔧 [ea-alert-line] {text}")
        except LineApiError as exc:
            # 管理者通知が送れないこと自体でジョブを落とさない（本来の通知が優先）
            logger.error("管理者通知の送信に失敗: %s / 内容: %s", exc, text)
