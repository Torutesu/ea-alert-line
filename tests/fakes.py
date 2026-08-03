"""ジョブテスト共用のフェイク。"""


class FakeNotifier:
    def __init__(self, broadcast_error=None):
        self.broadcasts = []
        self.admin_notices = []
        self.broadcast_error = broadcast_error  # 指定すると broadcast が必ず失敗する

    def broadcast(self, text):
        self.broadcasts.append(text)
        if self.broadcast_error is not None:
            raise self.broadcast_error

    def push(self, to, text):
        raise AssertionError("ジョブはpushを直接呼ばない")

    def notify_admin(self, text):
        self.admin_notices.append(text)


class FakeHttp:
    """URL→レスポンス本文の辞書を返すフェイクGET。

    値に例外を入れておくと、そのURLの取得が失敗する状況を再現できる。
    """

    def __init__(self, responses):
        self.responses = responses
        self.requested = []

    def __call__(self, url, **kwargs):
        self.requested.append(url)
        value = self.responses[url]
        if isinstance(value, Exception):
            raise value
        return value
