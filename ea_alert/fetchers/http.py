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
