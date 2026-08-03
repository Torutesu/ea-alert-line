from __future__ import annotations

import time

import requests

USER_AGENT = "ea-alert-line/1.0 (personal notification bot)"

# 4xxは再送しても同じ結果になるのが基本。ただし 408/429 は待てば通ることがある。
RETRIABLE_STATUS = {408, 429, 500, 502, 503, 504}


def get(url: str, *, retries: int = 3, timeout: int = 15) -> str:
    """UA明示・指数バックオフ付きGET。最終試行も失敗したら例外を投げ直す。"""
    for attempt in range(retries):
        try:
            resp = requests.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=timeout
            )
        except requests.RequestException:
            if attempt == retries - 1:
                raise
        else:
            if resp.status_code >= 400:
                # 403（bot対策など）は即時リトライしても無駄なので待たずに投げる
                if resp.status_code not in RETRIABLE_STATUS or attempt == retries - 1:
                    resp.raise_for_status()
            else:
                if resp.apparent_encoding:
                    resp.encoding = resp.apparent_encoding
                return resp.text
        time.sleep(2**attempt)
    raise AssertionError("unreachable")
