from pathlib import Path
import time
from common import discover_week_pages, scrape_week, read_json, write_json, dedupe

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/influenza_history.json"

def main():
    data=read_json(OUT)
    existing={(x["year"],x["week"]) for x in data.get("weeks",[])}
    pages=discover_week_pages(2025)
    pending=[p for p in pages if (p.year,p.week) not in existing]
    if not pending:
        print("新しい週はありません。")
        return
    new=[]
    for p in pending:
        try:
            w=scrape_week(p)
            new.append(w)
            print(f"added {p.year} W{p.week:02d}: {w['prefecture']}")
        except Exception as e:
            print(f"skip {p.year} W{p.week:02d}: {e}")
        time.sleep(.45)
    data["weeks"]=dedupe(data.get("weeks",[])+new)
    data.setdefault("meta",{})["weeks_ok"]=len(data["weeks"])
    write_json(OUT,data)
    print(f"updated {OUT} (+{len(new)})")

if __name__=="__main__":
    main()
