v58 — 最終更新日時の自動表示

差し替え:
- index.html
- app.js
- scripts/update.py
- scripts/backfill.py

追加:
- home-v58.css

そのまま:
- styles.css
- contact.html / contact.css / thanks.html
- analytics.js
- generate_ai_comment.py

導入直後:
GitHub Actions の Update influenza data を1回手動実行してください。
既存JSONに updated_at が無ければ、その時刻を初期値として保存します。
以後は新しい週を取得した時だけ updated_at を更新します。
