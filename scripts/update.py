from pathlib import Path
import time
from common import discover_week_pages, scrape_week, read_json, write_json, dedupe

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/influenza_history.json"

def main():
    data=read_json(OUT)
    weeks=data.get("weeks",[])

    # 新しい週に加え、既存週でも age_groups が未取得なら再取得する。
    existing={(x["year"],x["week"]):x for x in weeks}
    pages=discover_week_pages(2025)

    pending=[]
    for p in pages:
        old=existing.get((p.year,p.week))
        if old is None or not old.get("age_groups"):
            pending.append(p)

    if not pending:
        print("新しい週・年代別未取得週はありません。")
        return

    refreshed=[]
    for p in pending:
        try:
            w=scrape_week(p)
            refreshed.append(w)
            print(
                f"updated {p.year} W{p.week:02d}: "
                f"{w['prefecture']} / age_groups={len(w.get('age_groups',{}))}"
            )
        except Exception as e:
            print(f"skip {p.year} W{p.week:02d}: {e}")
        time.sleep(.45)

    # 同じ year/week は refreshed 側を優先して置換。
    data["weeks"]=dedupe(weeks+refreshed)

    meta=data.setdefault("meta",{})
    meta["weeks_ok"]=len(data["weeks"])
    meta["age_unit"]="報告数（人）"
    meta["age_groups"]=["0歳","1～4歳","5～9歳","10～14歳","15～19歳","20～59歳","60歳以上"]
    meta["weeks_with_age_data"]=sum(1 for w in data["weeks"] if w.get("age_groups"))

    write_json(OUT,data)
    print(f"updated {OUT} (+/refresh {len(refreshed)})")

if __name__=="__main__":
    main()
