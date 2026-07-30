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
