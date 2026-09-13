v30 右カラム重なり修正版

原因:
- v29では凡例(map-side)がmap-control-columnの外側に残っていたため、
  既存のabsolute配置CSSが効いてコントロール上に重なっていました。

修正:
- 凡例を右側のmap-control-column内へ移動
- TIME SLIDERの下に凡例を縦積み
- 右カラム内ではabsolute指定を強制解除
- 1366px級では右カラム260pxに調整

差し替え:
- index.html
- styles.css
