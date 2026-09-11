import json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
data=json.loads((ROOT/"data/influenza_history.json").read_text(encoding="utf-8"))
idx={(x["year"],x["week"]):x for x in data.get("weeks",[])}

checks={
    (2025,1):21.97,
    (2025,36):0.27,
    (2025,43):2.05,
    (2026,34):1.65,
    (2026,36):6.13,
}

errors=[]
for k,expected in checks.items():
    got=idx.get(k,{}).get("prefecture")
    if got is None or abs(float(got)-expected)>0.011:
        errors.append(f"{k}: expected {expected}, got {got}")

weeks=len(data.get("weeks",[]))
if weeks != 88:
    errors.append(f"expected 88 weeks, got {weeks}")

if errors:
    print("VERIFY FAILED")
    for e in errors:
        print(" -",e)
    sys.exit(1)

print("VERIFY OK")
print("weeks:",weeks)
for k,expected in checks.items():
    item=idx[k]
    method=item.get("verification",{}).get("method")
    print(f"{k[0]} W{k[1]:02d}: {item['prefecture']} (expected {expected}) [{method}]")
