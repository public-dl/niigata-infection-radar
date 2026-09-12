v22 QRコード表示修正版

原因:
- QRコード画像を assets フォルダの別ファイルとして参照していたため、
  画像ファイルがGitHub/Netlify側に反映されていない場合に破損画像になっていました。

修正:
- QRコード画像を index.html 内に直接埋め込み（Base64 data URI）
- これにより外部画像ファイルへの依存をなくしました
- index.html だけでもQRコードが表示されます

差し替え対象:
- index.html
（styles.css / app.js はそのままでOK）
