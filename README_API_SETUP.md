# OpenAI API連携 v31

## 目的
新潟県の `data/influenza_history.json` 全体から、最新週についてAIが週次コメントを生成し、
Webサイトの「今週の流行分析」に表示します。

生成ファイル:
- `data/ai_comment.json`

生成スクリプト:
- `scripts/generate_ai_comment.py`

GitHub Actions:
- `.github/workflows/generate_ai_comment.yml`

使用モデル:
- `gpt-5.6-luna`

## 重要
APIキーをHTML / JavaScript / GitHubリポジトリに直接書かないでください。
必ずGitHub ActionsのRepository Secretに保存します。

## GitHubでの設定手順

1. OpenAI PlatformでAPIキーを作成する
2. GitHubの対象リポジトリを開く
3. `Settings`
4. `Secrets and variables`
5. `Actions`
6. `New repository secret`
7. Name: `OPENAI_API_KEY`
8. Secret: 作成したOpenAI APIキー
9. 保存

## 最初の実行

GitHub:
`Actions` → `Generate AI weekly insight` → `Run workflow`

成功すると:
`data/ai_comment.json`
が自動で作成・コミットされます。

## 自動実行

現在のworkflowは毎日19:00（日本時間）にチェックします。

ただし、`data/ai_comment.json` がすでに最新週に対応している場合、
APIは呼ばずに終了します。

このため毎日workflowが動いても、通常は週1回だけAPI利用になります。

## Web側の動作

`app.js` は最初に:
`data/ai_comment.json`
を読みます。

AIコメントが最新週なら:
- AI WEEKLY INSIGHT
- 今週の流行分析
- AI自動生成

を表示します。

以下の場合:
- AI JSONがまだ無い
- API生成が失敗した
- AI JSONが古い週のもの

従来の新潟県週報の `topic` に自動で戻ります。

## AIへ渡すデータ

- 最新週の全県値
- 前週
- 前々週
- 前週比
- 前年同週
- 13地域の最新値ランキング
- 直近13週の全県推移
- 1 / 10 / 30 の参考水準

## AIが出力する項目

- headline
- summary
- trend
- regional
- year_on_year

後でA4 PDFにもこのJSONをそのまま利用できます。

## 任意設定

モデルを変える場合:
workflowの

`OPENAI_MODEL: gpt-5.6-luna`

を変更します。

強制再生成:
GitHub Actionsで一時的に
`FORCE_AI_COMMENT=true`
を環境変数に設定すると、同じ週でも再生成できます。
