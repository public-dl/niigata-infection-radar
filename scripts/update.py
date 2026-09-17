from pathlib import Path
from datetime import datetime, timezone, timedelta
import time
from common import discover_week_pages, scrape_week, read_json, write_json, dedupe

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/influenza_history.json"
JST=timezone(timedelta(hours=9))

def now_jst_iso():
    return datetime.now(JST).isoformat(timespec="seconds")


def main():
    data=read_json(OUT)
    weeks=data.get("weeks",[])

    existing={(x["year"],x["week"]):x for x in weeks}
    pages=discover_week_pages(2025)

    latest_page=max(pages,key=lambda p:(p.year,p.week))
    stored_latest=max(
        weeks,
        key=lambda w:(int(w.get("year",0)),int(w.get("week",0))),
        default=None
    )

    print(
        f"県一覧の最新週: {latest_page.year} W{latest_page.week:02d} "
        f"{latest_page.url}"
    )
    if stored_latest:
        print(
            f"保存済み最新週: {stored_latest.get('year')} "
            f"W{int(stored_latest.get('week',0)):02d} "
            f"/ {stored_latest.get('prefecture')}"
        )
    else:
        print("保存済み最新週: なし")

    # 新週だけでなく、年代別データが無い週も再取得する。
    # 今回追加した地域別実数は、表示に必要な「最新・前週」の2週だけ
    # 初回に補完する。以後の新週は scrape_week() で自動保存される。
    pages_sorted=sorted(pages,key=lambda p:(p.year,p.week))
    recent_region_keys={(p.year,p.week) for p in pages_sorted[-2:]}

    pending=[]
    new_keys=set()
    for p in pages:
        key=(p.year,p.week)
        old=existing.get(key)
        if old is None:
            new_keys.add(key)
        if (
            old is None
            or not old.get("age_counts")
            or not old.get("age_per_sentinel")
            or (key in recent_region_keys and not old.get("region_counts"))
        ):
            pending.append(p)

    if not pending:
        meta=data.setdefault("meta",{})
        if not meta.get("updated_at"):
            meta["updated_at"]=now_jst_iso()
            meta["updated_by"]="scripts/update.py"
            write_json(OUT,data)
            print(f"更新日時を初期化しました: {meta['updated_at']}")
        else:
            print("新しい週・年代別未取得週・地域別実数未取得週はありません。")
        return

    refreshed=[]
    failures=[]

    for p in pending:
        key=(p.year,p.week)
        try:
            w=scrape_week(p)
            refreshed.append(w)
            print(
                f"updated {p.year} W{p.week:02d}: "
                f"{w['prefecture']} / "
                f"age_counts={len(w.get('age_counts',{}))} / "
                f"age_per_sentinel={len(w.get('age_per_sentinel',{}))} / "
                f"region_counts={len(w.get('region_counts',{}))}"
            )
        except Exception as e:
            failures.append((p.year,p.week,str(e),key in new_keys))
            print(f"ERROR {p.year} W{p.week:02d}: {e}")
        time.sleep(.45)

    # 重要:
    # 新しく県一覧に登場した週の取得失敗を「成功扱い」にしない。
    # 旧週の年代別補完失敗だけなら継続可能だが、新週失敗はActionを赤にして知らせる。
    fatal=[x for x in failures if x[3]]
    if fatal:
        details="; ".join(
            f"{y} W{w:02d}: {err}" for y,w,err,_ in fatal
        )
        raise RuntimeError(
            "新しく公開された週の取得に失敗しました。"
            "古いデータのまま正常終了することを防止します。 "
            + details
        )

    data["weeks"]=dedupe(weeks+refreshed)

    # 県一覧の最新週が保存データに入ったことを必ず確認する。
    final_keys={(int(w["year"]),int(w["week"])) for w in data["weeks"]}
    latest_key=(latest_page.year,latest_page.week)
    if latest_key not in final_keys:
        raise RuntimeError(
            f"県一覧の最新週 {latest_page.year} W{latest_page.week:02d} "
            "が influenza_history.json に入りませんでした。"
        )

    meta=data.setdefault("meta",{})
    meta["weeks_ok"]=len(data["weeks"])
    meta["age_count_unit"]="報告数（人）"
    meta["age_per_sentinel_unit"]="人/定点"
    meta["age_groups"]=["0歳","1～4歳","5～9歳","10～14歳","15～19歳","20～59歳","60歳以上"]
    meta["weeks_with_age_data"]=sum(
        1 for w in data["weeks"]
        if w.get("age_counts") and w.get("age_per_sentinel")
    )
    meta["weeks_with_region_counts"]=sum(
        1 for w in data["weeks"] if w.get("region_counts")
    )

    # 旧キーは今後使わないので meta から除去
    meta.pop("age_unit",None)

    if refreshed:
        meta["updated_at"]=now_jst_iso()
        meta["updated_by"]="scripts/update.py"

    write_json(OUT,data)

    newest=max(
        data["weeks"],
        key=lambda w:(int(w.get("year",0)),int(w.get("week",0)))
    )
    print(
        f"updated {OUT} (+/refresh {len(refreshed)}) / "
        f"latest={newest.get('year')} W{int(newest.get('week',0)):02d} "
        f"/ {newest.get('prefecture')}"
    )

if __name__=="__main__":
    main()
