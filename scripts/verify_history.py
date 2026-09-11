import json, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
p=ROOT/"data/influenza_history.json"
data=json.loads(p.read_text(encoding="utf-8"))
idx={(x["year"],x["week"]):x for x in data.get("weeks",[])}

checks = {
    (2025, 1): 21.97,
    (2025, 43): 2.05,
    (2026, 34): 1.65,
    (2026, 36): 6.13,
}

errors=[]
for k,expected in checks.items():
    got=idx.get(k,{}).get("prefecture")
    if got is None or abs(float(got)-expected)>0.011:
        errors.append(f"{k}: expected {expected}, got {got}")

bad_values = {
    (2025,36): 11.58,
    (2025,43): 0.27,
    (2026,34): 0.18,
}
for k,bad in bad_values.items():
    got=idx.get(k,{}).get("prefecture")
    if got is not None and abs(float(got)-bad)<0.011:
        errors.append(f"{k}: known wrong value {bad} was selected")

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
    print(f"{k[0]} W{k[1]:02d}: {idx[k]['prefecture']} (expected {expected})")
