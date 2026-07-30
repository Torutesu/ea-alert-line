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

### 2. GitHub Actions での運用（採用中）

このリポジトリは GitHub Actions のスケジュール実行で動く（サーバー不要・パブリックリポジトリなら無料）。

| ワークフロー | スケジュール | 内容 |
|---|---|---|
| `.github/workflows/fetch-daily.yml` | 21:00 UTC（= 06:00 JST） | カレンダー取得・DB更新 |
| `.github/workflows/send-digest.yml` | 00:00 UTC（= 09:00 JST） | 朝ダイジェスト送信 |
| `.github/workflows/tick.yml` | 5分ごと | 直前アラート・発言予告・速報 |

セットアップ:

1. リポジトリの **Settings → Secrets and variables → Actions** で
   `LINE_CHANNEL_ACCESS_TOKEN` にチャネルアクセストークンを登録
   （未登録の間、tick / digest はスキップされ、失敗にはならない）
2. **Actions タブでワークフローを有効化**（フォーク直後は手動で有効化が必要）
3. 動作確認は各ワークフローの **Run workflow**（workflow_dispatch）で手動実行

仕組みメモ:

- 状態DB（`data/ea_alert.db`）はワークフローが**リポジトリにコミットして永続化**する
  （`chore: 状態DB更新` コミットが自動で積まれるのは正常動作）
- 3ワークフローは同一 concurrency グループで直列実行され、DBコミットの競合を防ぐ
- GitHub Actions の cron は数分〜15分程度遅れることがある。窓判定はその前提で
  設計されており通知漏れにはならないが、「30分前」が実際は15〜25分前になることがある
- ※ tick の初回実行はブートストラップとして既存ニュースを既読化するだけで通知しない
- パブリックリポジトリの scheduled workflow は60日間リポジトリに活動がないと
  自動停止するが、本ボットはDBコミットで常に活動があるため実質問題ない

### 3. ローカル/VPSでの運用（代替）

```bash
git clone <このリポジトリ> && cd ea-alert-line
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export LINE_CHANNEL_ACCESS_TOKEN="（発行したトークン）"
mkdir -p data logs
.venv/bin/pytest -q   # 動作確認
```

手動でジョブを1回ずつ実行して疎通確認:

```bash
.venv/bin/python -m ea_alert.jobs.fetch_daily --config config.yaml
.venv/bin/python -m ea_alert.jobs.send_digest --config config.yaml
.venv/bin/python -m ea_alert.jobs.tick --config config.yaml
```

cron設定（VPSの場合。時刻はJST前提、JST以外のTZなら `CRON_TZ=Asia/Tokyo` を付ける）:

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
