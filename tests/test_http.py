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
