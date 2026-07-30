from __future__ import annotations

from ea_alert.models import Event

# gaikaex カレンダーの flag alt（14か国＋スイス）→ 通貨コード
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
    "スイス": "CHF",
}


def indicator_matches(
    event: Event, currencies: list[str], min_importance: int
) -> bool:
    """経済指標が通知対象か判定する。要人発言（speech/statement）には適用しない。"""
    if event.importance < min_importance:
        return False
    currency = COUNTRY_TO_CURRENCY.get(event.country)
    return currency in currencies
