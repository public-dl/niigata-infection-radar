# 新潟インフルエンザレーダー

新潟県の公表データをもとに、インフルエンザの流行状況を見やすく可視化するWebサイトです。

- 公開サイト: https://public-dl.github.io/niigata-infection-radar/
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

GitHub Pages が `main` ブランチのルートを公開します。GitHub Actions によるデータ確認は、木曜・金曜の12:17／15:17／18:17、月曜〜水曜の18:17（日本時間）に実行します。実行開始はGitHub側の混雑等で遅れる場合があります。

処理の流れは次のとおりです。

1. 新潟県の最新週データを取得し、履歴に変更があれば先にcommit / push
2. `scripts/weekly_outputs.py` で履歴・AI・PDFの最新状態を判定
3. AIが欠落または対象週が古ければ生成し、PDF生成前にcommit / push
4. PDFが欠落・古い・入力と不整合なら再生成
5. PDFと `reports/latest.meta.json` を検証し、commit / push
6. GitHub Pagesで公開内容を更新

データ差分がなくても古いAI/PDFは再試行します。すべて最新なら生成をスキップします。書き込み系5 Workflowは同じブランチの共通concurrencyで実行を直列化します。

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
reports/template/report.html
reports/template/report.css
```

出力先:

```text
reports/latest.pdf
```

PDFでは、前週からの増減を次のように表示します。

- 増加: 赤
- 減少: 青
- 変化なし: グレー

PDFと同時に `reports/latest.meta.json` を生成し、対象年・週およびPDF・AI・履歴のSHA-256を記録します。両ファイルはセットで管理してください。

`reports/template/weekly_report_rendered.html` はテンプレートにデータを埋め込んだPDF変換用中間HTMLです。現行処理が毎回生成します。現在はGit管理を継続しています。

## お問い合わせ

`contact.html` は専用のWeb3Forms Access Keyで `https://api.web3forms.com/submit` に送信します。JavaScriptで成功応答を確認した場合だけ完了表示と入力クリアを行い、エラー時は入力を保持します。GitHub Pages側に送信用サーバーは不要です。

## AI週次分析

最新週のAIコメントが存在しない、または対象週が一致しない場合に、

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

## テスト

```bash
pip install -r requirements-test.txt
python -B -m unittest discover -s tests -v
node --test tests/test_contact_submit.cjs
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
