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
