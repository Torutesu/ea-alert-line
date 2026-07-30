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
