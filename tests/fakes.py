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
