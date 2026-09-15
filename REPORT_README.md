# 新潟県インフルエンザ週次レポート v1

## 追加・差し替えファイル
- `scripts/generate_weekly_report.py`
- `reports/template/report.html`
- `reports/template/report.css`

## 既存データをそのまま利用
- `data/influenza_history.json`
- `data/ai_comment.json`

`generate_weekly_report.py` は最新週を自動選択し、Web側と同じAIコメントをPDFへ反映します。

地図は `data/niigata_municipality.geojson` があればローカルファイルを使い、無ければ公開GeoJSONを取得してSVG化します。GitHub Actionsではネットワーク取得できます。取得できない環境ではレイアウト確認用の簡易地図にフォールバックします。

シグナル色はWeb版と共通です。
- 1未満: 青
- 1以上10未満: 黄
- 10以上30未満: 赤
- 30以上: 紫

実行:

```bash
python scripts/generate_weekly_report.py
```

出力:
- `reports/latest.pdf`

A4横・1ページです。
