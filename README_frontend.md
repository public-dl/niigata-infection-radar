# 新潟感染症レーダー フロントエンド v1

## 配置
以下3ファイルをリポジトリ直下へ置きます。

- index.html
- styles.css
- app.js

既存の `data/influenza_history.json` をそのまま読み込みます。

## 外部ライブラリ
- Chart.js
- Leaflet
- SmartNews SMRI japan-topography GeoJSON（国土数値情報由来）

## 主な機能
- 最新値 / 前週 / 前々週 / 前週比
- 新潟県週報の「今週のポイント」
- 88週の横スクロール時系列グラフ
- 最新へボタン
- 前年同週比較
- 13地域ランキング
- 30市町村の実境界による地域別色分け地図
- レスポンシブ対応
