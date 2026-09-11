from pathlib import Path
import argparse, json, time
from common import discover_week_pages, scrape_week, write_json, dedupe

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/influenza_history.json"
FAIL=ROOT/"data/backfill_failures.json"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--start-year",type=int,default=2025)
    ap.add_argument("--delay",type=float,default=0.45)
    args=ap.parse_args()

    pages=discover_week_pages(args.start_year)
    print(f"discovered {len(pages)} weekly pages")
    weeks=[]; failures=[]
    for i,wp in enumerate(pages,1):
        try:
            w=scrape_week(wp)
            weeks.append(w)
            print(f"[{i}/{len(pages)}] OK {wp.year} W{wp.week:02d}: {w['prefecture']} / regions={len(w['regions'])}")
        except Exception as e:
            failures.append({"year":wp.year,"week":wp.week,"url":wp.url,"error":str(e)})
            print(f"[{i}/{len(pages)}] FAIL {wp.year} W{wp.week:02d}: {e}")
        time.sleep(args.delay)

    payload={
      "meta":{
        "source":"新潟県感染症情報（週報）",
        "index_url":"https://www.pref.niigata.lg.jp/sec/kanyaku/1232482573101.html",
        "disease":"インフルエンザ",
        "unit":"定点当たり報告数",
        "generated_by":"scripts/backfill.py",
        "weeks_ok":len(weeks),
        "weeks_failed":len(failures)
      },
      "weeks":dedupe(weeks)
    }
    write_json(OUT,payload)
    write_json(FAIL,failures)
    print(f"\nwritten: {OUT}")
    print(f"failures: {len(failures)} -> {FAIL}")
    if failures:
        print("一部の週は構造差異等で自動抽出できませんでした。failureログを確認してください。")

if __name__=="__main__":
    main()
