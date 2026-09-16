# 新潟インフルエンザレーダー

新潟県の公表データをもとに、インフルエンザの流行状況を見やすく可視化するWebサイトです。

- 公開サイト: https://niigata-infection-radar.netlify.app/
- データ出典: 新潟県「感染症情報（週報）」
- 運営: CivITech

## 主な機能

- 新潟県全体の定点当たり報告数
- 前週との増減表示
- 13地域の流行状況マップ
- 地域別ランキング
- 県全体の時系列推移
- 前年同期との比較
- 年代別の最新週比較
- 年代別の時系列推移
- 年代別ヒートマップ
- AIによる週次分析
- A4横1ページの週次PDFレポート
- PDFレポートの公開
- SEO / OGP対応
- Google Analytics 4 によるアクセス解析
- sitemap.xml による検索エンジン向けサイトマップ

## 自動更新

GitHub Actions により、原則として毎週木曜日 19:30（日本時間）に自動更新します。

処理の流れは次のとおりです。

1. 新潟県の最新週データを取得
2. `data/influenza_history.json` を更新
3. 最新週をもとにAI週次分析を生成
4. `data/ai_comment.json` を更新
5. 最新データとAI分析をもとに週次PDFを生成
6. `reports/latest.pdf` を更新
7. 変更ファイルをGitHubへcommit / push
8. Netlifyが更新を検知してサイトを再デプロイ

自動更新ワークフロー:

```text
.github/workflows/update-influenza.yml
```

手動実行も GitHub Actions の `workflow_dispatch` から可能です。

## データ

主要な履歴データ:

```text
data/influenza_history.json
```

AI週次分析:

```text
data/ai_comment.json
```

週次PDF:

```text
reports/latest.pdf
```

サイト側では `influenza_history.json` を読み込み、最新週を自動判定して表示します。

## 13地域

地域別表示は、新潟県の公表地域単位に基づいています。

- 新潟
- 新発田
- 村上
- 長岡
- 柏崎
- 上越
- 糸魚川
- 南魚沼
- 十日町
- 佐渡
- 新津
- 三条
- 魚沼

※ 表示上の地域名は用途に応じて「新潟市」「新津※」などの表記を使用する場合があります。

## 流行水準の表示

定点当たり報告数を次の4段階で表示します。

| 水準 | 定点当たり報告数 |
|---|---:|
| 青 | 1未満 |
| 黄 | 1以上10未満 |
| 赤 | 10以上30未満 |
| 紫 | 30以上 |

これらは流行状況を見やすくするための表示であり、公式の注意報・警報の発令そのものを示すものではありません。

## PDF週次レポート

週次レポートは次のファイルから生成します。

```text
scripts/generate_weekly_report.py
report.html
report.css
```

出力先:

```text
reports/latest.pdf
```

PDFでは、前週からの増減を次のように表示します。

- 増加: 赤
- 減少: 青
- 変化なし: グレー

## AI週次分析

最新週のデータ更新後に、

```text
scripts/generate_ai_comment.py
```

を実行し、AI分析を生成します。

GitHub Actions では `OPENAI_API_KEY` を Repository Secret として使用します。

## 初回データ取得 / 過去データ

過去データの一括取得には、必要に応じて次のスクリプトを使用します。

```text
scripts/backfill.py
```

例:

```bash
python scripts/backfill.py --start-year 2025
```

## ローカル実行

Python 3.12 を推奨します。

依存パッケージ:

```bash
pip install -r requirements.txt
pip install --upgrade openai weasyprint
```

最新データ取得:

```bash
python scripts/update.py
```

AI週次分析生成:

```bash
python scripts/generate_ai_comment.py
```

PDF生成:

```bash
python scripts/generate_weekly_report.py
```

## 検索・SNS対応

トップページでは以下を設定しています。

- title / description
- canonical
- robots
- OGP
- X / Twitter Card
- JSON-LD
- `sitemap.xml`

OGP画像:

```text
ogp.png
```

サイトマップ:

```text
sitemap.xml
```

## アクセス解析

Google Analytics 4 を利用しています。

測定用スクリプト:

```text
analytics.js
```

## 注意事項

出典: 新潟県「感染症情報（週報）」

本サイトは公表データを見やすく整理したもので、診断・受診判断を行うものではありません。

公表データの更新時刻や公開形式の変更等により、自動更新が一時的に失敗する場合があります。

---

Powered by CivITech
