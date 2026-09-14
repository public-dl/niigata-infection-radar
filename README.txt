v54: アクセス解析 + お問い合わせフォーム

配置するファイル:
- index.html
- analytics.js
- contact.html
- contact.css
- thanks.html

Google Analytics:
analytics.js の
  const MEASUREMENT_ID = "G-XXXXXXXXXX";
を実際の GA4 測定IDに置き換えるだけです。
未設定のままではアクセス情報を送信しません。

Netlify Forms:
Netlify管理画面 > Forms > Enable form detection を有効にしてからデプロイしてください。
送信内容は Netlify > Forms > influenza-radar-contact で確認できます。

フォーム項目: 所属・団体名 / お名前 / メールアドレス / お問い合わせ内容
