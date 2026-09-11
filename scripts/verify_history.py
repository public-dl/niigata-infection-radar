"""
バックフィル後の最低限の回帰チェック。
既知の公開値と一致しなければ exit 1。
"""
import json, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
p=ROOT/"data/influenza_history.json"
data=json.loads(p.read_text(encoding="utf-8"))
idx={(x["year"],x["week"]):x for x in data.get("weeks",[])}

checks = {
    (2025,1): 21.97,
    (2026,36): 6.13,
}
errors=[]
for k,expected in checks.items():
    got=idx.get(k,{}).get("prefecture")
    if got is None or abs(float(got)-expected)>0.011:
        errors.append(f"{k}: expected {expected}, got {got}")

# 2025 W36 は新型コロナの11.58を誤取得していないことだけ確認
got=idx.get((2025,36),{}).get("prefecture")
if got is not None and abs(float(got)-11.58)<0.011:
    errors.append("2025 W36: COVID-19の11.58を誤取得しています")

if errors:
    print("VERIFY FAILED")
    for e in errors: print(" -",e)
    sys.exit(1)

print("VERIFY OK")
print("weeks:",len(data.get("weeks",[])))
