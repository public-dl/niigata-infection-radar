# v33 AIコメント / Web / A4 PDF 共通利用版

## 共通データ
WebとPDFは同じ `data/ai_comment.json` を読みます。

- Web: `app.js` が `data/ai_comment.json` を表示
- PDF: `scripts/generate_weekly_report.py` が同じJSONを読み込む

これにより、WebとPDFでコメント内容が食い違いません。

## 自動処理
`.github/workflows/generate_weekly_outputs.yml`

1. `scripts/generate_ai_comment.py`
2. `data/ai_comment.json`
3. `scripts/generate_weekly_report.py`
4. `reports/latest.pdf`
5. `reports/niigata_influenza_report_YYYYWww.pdf`
6. まとめてGitHubへコミット

## Web側
ヘッダーに `PDFレポート` を追加しました。
リンク先は常に `reports/latest.pdf` です。

## PDF側
PDFはA4横1枚です。

- AIコメント: `data/ai_comment.json`
- 最新/前週/前々週: `data/influenza_history.json`
- 地域ランキング: 最新週のregions
- 地図: 最新週のregions + 新潟県GeoJSON
- グラフ: 直近13週 + 前年同期
- 前年同期: 同じ週番号で比較
- QRコード: `assets/qr-niigata-influenza-radar.png`

## 注意
既存の `Generate AI weekly insight` workflow は
`generate_weekly_outputs.yml` に置き換えてください。
2つを同時に残すとAI生成処理が重複します。

## 次回更新
週報JSONが更新された後、このworkflowを実行すれば、
AIコメントとPDFが同じ最新週を基準に更新されます。
