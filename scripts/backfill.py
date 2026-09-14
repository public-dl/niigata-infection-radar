from pathlib import Path
import argparse, time
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
    if not pages:
        raise RuntimeError("週報ページが0件です。処理を中止します。")

    weeks=[]; failures=[]
    age_ok=0

    for i,wp in enumerate(pages,1):
        try:
            w=scrape_week(wp)
            weeks.append(w)

            counts=len(w.get("age_counts",{}))
            rates=len(w.get("age_per_sentinel",{}))
            if counts and rates:
                age_ok+=1

            print(
                f"[{i}/{len(pages)}] OK {wp.year} W{wp.week:02d}: "
                f"{w['prefecture']} / regions={len(w['regions'])} / "
                f"age_counts={counts} / age_per_sentinel={rates}"
            )

            if not counts or not rates:
                diag=w.get("_age_parser",{}).get("diagnostics",[])
                if diag:
                    print("   age diagnostics:", " | ".join(diag[:3]))

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
        "age_count_unit":"報告数（人）",
        "age_per_sentinel_unit":"人/定点",
        "age_groups":["0歳","1～4歳","5～9歳","10～14歳","15～19歳","20～59歳","60歳以上"],
        "generated_by":"scripts/backfill.py",
        "weeks_discovered":len(pages),
        "weeks_ok":len(weeks),
        "weeks_with_age_data":age_ok,
        "weeks_failed":len(failures)
      },
      "weeks":dedupe(weeks)
    }

    write_json(OUT,payload)
    write_json(FAIL,failures)

    print(f"\nwritten: {OUT}")
    print(f"success: {len(weeks)} / discovered: {len(pages)}")
    print(f"age data: {age_ok} / success: {len(weeks)}")
    print(f"failures: {len(failures)} -> {FAIL}")

    if len(weeks) == 0:
        raise RuntimeError("週報は検出できましたが、Excelから1週も抽出できませんでした。failureログを確認してください。")

if __name__=="__main__":
    main()
