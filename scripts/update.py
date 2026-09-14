from pathlib import Path
import time
from common import discover_week_pages, scrape_week, read_json, write_json, dedupe

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/influenza_history.json"

def main():
    data=read_json(OUT)
    weeks=data.get("weeks",[])

    existing={(x["year"],x["week"]):x for x in weeks}
    pages=discover_week_pages(2025)

    # 新週だけでなく、
    # age_counts / age_per_sentinel のどちらかが無い既存週も再取得する。
    pending=[]
    for p in pages:
        old=existing.get((p.year,p.week))
        if (
            old is None
            or not old.get("age_counts")
            or not old.get("age_per_sentinel")
        ):
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
                f"{w['prefecture']} / "
                f"age_counts={len(w.get('age_counts',{}))} / "
                f"age_per_sentinel={len(w.get('age_per_sentinel',{}))}"
            )
        except Exception as e:
            print(f"skip {p.year} W{p.week:02d}: {e}")
        time.sleep(.45)

    data["weeks"]=dedupe(weeks+refreshed)

    meta=data.setdefault("meta",{})
    meta["weeks_ok"]=len(data["weeks"])
    meta["age_count_unit"]="報告数（人）"
    meta["age_per_sentinel_unit"]="人/定点"
    meta["age_groups"]=["0歳","1～4歳","5～9歳","10～14歳","15～19歳","20～59歳","60歳以上"]
    meta["weeks_with_age_data"]=sum(
        1 for w in data["weeks"]
        if w.get("age_counts") and w.get("age_per_sentinel")
    )

    # 旧キーは今後使わないので meta から除去
    meta.pop("age_unit",None)

    write_json(OUT,data)
    print(f"updated {OUT} (+/refresh {len(refreshed)})")

if __name__=="__main__":
    main()
