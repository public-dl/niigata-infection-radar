from __future__ import annotations
import io, json, re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
import requests
from bs4 import BeautifulSoup
from openpyxl import load_workbook

INDEX_URL = "https://www.pref.niigata.lg.jp/sec/kanyaku/1232482573101.html"
UA = "Niigata-Infection-Radar/2.1 (public-data visualization)"
REGIONS = ["新潟市","新発田","新津","三条","長岡","魚沼","南魚沼","十日町","柏崎","糸魚川","村上","佐渡","上越"]

# サイト表示用の年代区分。
# 元Excelが20～29歳、30～39歳…のように細分されている場合は下で自動集約する。
AGE_GROUPS = ["0歳","1～4歳","5～9歳","10～14歳","15～19歳","20～59歳","60歳以上"]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": UA,
    "Accept-Language":"ja,en-US;q=0.7,en;q=0.3"
})

def norm(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).replace("\u3000"," ").replace("\n"," ").replace("\r"," ")
    s = re.sub(r"\s+", "", s)
    s = s.replace("〜","～").replace("－","-").replace("―","-").replace("−","-")
    s = re.sub(r"[※＊*]+$", "", s)
    return s

def get(url: str, binary=False):
    r = SESSION.get(url, timeout=35)
    r.raise_for_status()
    if binary:
        return r.content
    raw = r.content
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(r.apparent_encoding or "cp932", errors="replace")

def abs_url(base, href):
    from urllib.parse import urljoin
    return urljoin(base, href)

@dataclass
class WeekPage:
    year:int
    week:int
    url:str

def discover_week_pages(start_year=2025):
    soup=BeautifulSoup(get(INDEX_URL),"html.parser")
    out=[]; seen=set()
    for a in soup.find_all("a",href=True):
        txt=a.get_text(" ",strip=True)
        m=re.search(r"令和\s*(\d+)\s*年\s*第\s*(\d+)\s*週",txt)
        if not m:
            continue
        y=2018+int(m.group(1)); w=int(m.group(2))
        if y < start_year:
            continue
        k=(y,w)
        if k not in seen:
            seen.add(k)
            out.append(WeekPage(y,w,abs_url(INDEX_URL,a["href"])))
    out.sort(key=lambda x:(x.year,x.week))
    if not out:
        raise RuntimeError("週報一覧から週ページを検出できませんでした。")
    return out

def parse_dates_from_page(soup, year, week):
    text=soup.get_text(" ",strip=True)
    m=re.search(rf"第\s*{week}\s*週.*?(\d+)月(\d+)日から.*?(\d+)月(\d+)日",text)
    if not m:
        return None,None
    sm,sd,em,ed=map(int,m.groups())
    sy=year; ey=year+(1 if em<sm else 0)
    if week==1 and sm==12:
        sy=year-1; ey=year
    try:
        return date(sy,sm,sd),date(ey,em,ed)
    except ValueError:
        return None,None

def reiwa_label(d1,d2):
    ry=d1.year-2018
    if d1.year==d2.year:
        return f"R{ry}/{d1.month}/{d1.day}–{d2.month}/{d2.day}"
    return f"R{ry}/{d1.month}/{d1.day}–R{d2.year-2018}/{d2.month}/{d2.day}"

def extract_topic(soup):
    text=soup.get_text("\n",strip=True)
    m=re.search(
        r"◆\s*インフルエンザ([\s\S]*?)(?=\n\s*◆|\n\s*警報を発令している疾患|$)",
        text
    )
    if not m:
        return ""
    return re.sub(r"\n{3,}","\n\n","インフルエンザ"+m.group(1)).strip()[:3000]

def extract_topic_prefecture_value(soup):
    topic=extract_topic(soup)
    if not topic:
        return None
    m=re.search(r"全県で\s*([0-9]+(?:\.[0-9]+)?)",topic)
    return float(m.group(1)) if m else None

def find_excel_url(soup,page_url):
    for a in soup.find_all("a",href=True):
        t=norm(a.get_text(" ",strip=True))
        href=a["href"]
        if "5類感染症定点把握対象疾患報告数" in t:
            return abs_url(page_url,href)
        if href.lower().endswith((".xlsx",".xlsm")) and "定点" in t:
            return abs_url(page_url,href)
    return None

def as_number(v):
    if isinstance(v,(int,float)) and not isinstance(v,bool):
        return float(v)
    if isinstance(v,str):
        s=v.strip().replace(",","")
        if re.fullmatch(r"-?\d+(?:\.\d+)?",s):
            return float(s)
    return None

def canonical_header(s):
    s=norm(s)
    if s in ("県計","全県","県全体"):
        return "県計"
    for r in REGIONS:
        if s==r:
            return r
    return None

def find_main_table(ws):
    """
    「地域振興局等管内別報告数」と明記された主表だけを返す。
    最近6週間推移や入院サーベイランスは対象外。
    """
    title_row=None
    for r in range(1, min(ws.max_row, 80)+1):
        for c in range(1, min(ws.max_column, 20)+1):
            s=norm(ws.cell(r,c).value)
            if "地域振興局等管内別報告数" in s:
                title_row=r
                break
        if title_row:
            break

    if title_row is None:
        return None

    header_row=None
    cols=None
    for r in range(title_row, min(ws.max_row, title_row+5)+1):
        found={}
        for c in range(1, min(ws.max_column, 30)+1):
            key=canonical_header(ws.cell(r,c).value)
            if key and key not in found:
                found[key]=c
        if len(found) >= 10 and "県計" in found:
            header_row=r
            cols=found
            break

    if header_row is None:
        return None

    flu_row=None
    for r in range(header_row+1, min(ws.max_row, header_row+12)+1):
        if norm(ws.cell(r,1).value) == "インフルエンザ":
            flu_row=r
            break

    if flu_row is None:
        return None

    value_row=None
    for r in range(flu_row, min(ws.max_row, flu_row+4)+1):
        left="".join(norm(ws.cell(r,c).value) for c in range(1, min(cols.values())))
        if "定点当" in left:
            value_row=r
            break

    if value_row is None:
        return None

    return {
        "title_row":title_row,
        "header_row":header_row,
        "flu_row":flu_row,
        "value_row":value_row,
        "cols":cols,
    }

# ---------- 年代別抽出 ----------

def parse_age_range_header(value):
    """
    年齢見出しを (下限, 上限) に正規化する。
    上限Noneは「以上」。
    例:
      0歳 -> (0,0)
      1～4歳 -> (1,4)
      20～29歳 -> (20,29)
      80歳以上 -> (80,None)
    """
    s=norm(value)
    if not s:
        return None

    # 年齢表にありがちな補助語を除去
    s=s.replace("年齢","").replace("年令","")
    s=s.replace("歳未満","未満")

    if s in ("0歳","0"):
        return (0,0)

    m=re.fullmatch(r"(\d+)～(\d+)歳?",s)
    if m:
        return (int(m.group(1)),int(m.group(2)))

    m=re.fullmatch(r"(\d+)-(\d+)歳?",s)
    if m:
        return (int(m.group(1)),int(m.group(2)))

    m=re.fullmatch(r"(\d+)歳?以上",s)
    if m:
        return (int(m.group(1)),None)

    # 「80～」のような表記
    m=re.fullmatch(r"(\d+)～",s)
    if m:
        return (int(m.group(1)),None)

    return None

def broad_age_group(age_range):
    lo, hi = age_range
    if lo == 0 and hi == 0:
        return "0歳"
    if lo >= 1 and hi is not None and hi <= 4:
        return "1～4歳"
    if lo >= 5 and hi is not None and hi <= 9:
        return "5～9歳"
    if lo >= 10 and hi is not None and hi <= 14:
        return "10～14歳"
    if lo >= 15 and hi is not None and hi <= 19:
        return "15～19歳"
    if lo >= 20 and hi is not None and hi <= 59:
        return "20～59歳"
    if lo >= 60:
        return "60歳以上"
    return None

def find_age_table(ws):
    """
    年齢階級の見出し行と、その近くにあるインフルエンザ行を探索する。
    「年齢別」「年齢階級別」等のタイトルが近い候補を優先する。
    """
    max_r=min(ws.max_row,180)
    max_c=min(ws.max_column,80)
    candidates=[]

    for r in range(1,max_r+1):
        age_cols={}
        for c in range(1,max_c+1):
            ar=parse_age_range_header(ws.cell(r,c).value)
            if ar and ar not in age_cols:
                age_cols[ar]=c

        if len(age_cols) < 5:
            continue

        # 近傍に「年齢」タイトルがあるか
        title_score=0
        title_row=None
        for rr in range(max(1,r-8),r+1):
            rowtext="".join(norm(ws.cell(rr,cc).value) for cc in range(1,min(max_c,20)+1))
            if "年齢" in rowtext:
                title_score=20
                title_row=rr
                break

        # 見出しの直後を優先してインフルエンザ行探索
        flu_row=None
        for rr in range(r+1,min(max_r,r+30)+1):
            left="".join(norm(ws.cell(rr,cc).value) for cc in range(1,min(min(age_cols.values()),10)+1))
            if "インフルエンザ" in left:
                flu_row=rr
                break

        if flu_row is None:
            continue

        score=len(age_cols)*3 + title_score - max(0,flu_row-r-5)
        candidates.append({
            "score":score,
            "title_row":title_row,
            "header_row":r,
            "flu_row":flu_row,
            "age_cols":age_cols,
        })

    if not candidates:
        return None

    candidates.sort(key=lambda x:x["score"],reverse=True)
    return candidates[0]

def parse_age_groups(wb, expected_total=None):
    """
    年代別報告数を抽出。
    戻り値:
      age_groups: サイト用7区分
      age_raw: Excelの元年齢階級
      age_parser: 診断情報

    単位は「報告数（人）」。
    """
    diagnostics=[]

    for ws in wb.worksheets:
        info=find_age_table(ws)
        if not info:
            diagnostics.append(f"{ws.title}: 年齢表なし")
            continue

        age_raw={}
        broad={k:0.0 for k in AGE_GROUPS}
        numeric_found=False

        for ar,c in info["age_cols"].items():
            raw=ws.cell(info["flu_row"],c).value
            n=as_number(raw)
            if n is None:
                n=0.0
            else:
                numeric_found=True

            lo,hi=ar
            raw_label=f"{lo}歳以上" if hi is None else (f"{lo}歳" if lo==hi else f"{lo}～{hi}歳")
            age_raw[raw_label]=round(float(n),4)

            g=broad_age_group(ar)
            if g:
                broad[g]+=float(n)

        # 候補表なのに完全空欄なら他シートも試す
        if not numeric_found and expected_total not in (None,0):
            diagnostics.append(f"{ws.title}: 年齢表候補だが数値なし")
            continue

        broad={k:round(v,4) for k,v in broad.items()}

        # 主表の県計実数が取れている場合は年代別合計と照合。
        # 1人程度のズレも原則異常扱いにするが、期待値なしなら照合しない。
        age_sum=round(sum(broad.values()),4)
        verification=None
        if expected_total is not None:
            verification={
                "expected_total":round(float(expected_total),4),
                "age_sum":age_sum,
                "difference":round(age_sum-float(expected_total),4),
            }
            if abs(age_sum-float(expected_total)) > 0.01:
                diagnostics.append(
                    f"{ws.title}: 年代別合計不一致 age_sum={age_sum} expected={expected_total}"
                )
                continue

        return {
            "age_groups":broad,
            "age_raw":age_raw,
            "age_unit":"報告数（人）",
            "_age_parser":{
                "sheet":ws.title,
                "title_row":info["title_row"],
                "header_row":info["header_row"],
                "flu_row":info["flu_row"],
                "raw_age_columns":len(info["age_cols"]),
                "verification":verification,
                "strategy":"age_table_by_headers_and_influenza_row"
            }
        }

    return {
        "age_groups":{},
        "age_raw":{},
        "age_unit":"報告数（人）",
        "_age_parser":{
            "strategy":"not_found",
            "diagnostics":diagnostics[:20]
        }
    }

def parse_influenza_excel(data):
    wb=load_workbook(io.BytesIO(data),data_only=True,read_only=False)
    diagnostics=[]

    main_result=None

    for ws in wb.worksheets:
        info=find_main_table(ws)
        if not info:
            diagnostics.append(f"{ws.title}: 主表を特定できず")
            continue

        vals={}
        for key,c in info["cols"].items():
            raw = ws.cell(info["value_row"],c).value
            n = as_number(raw)
            if key == "県計":
                if n is not None:
                    vals[key]=n
            else:
                vals[key]=0.0 if n is None else n

        # 実数行の県計も保存。年代別合計の検証に使う。
        prefecture_count=None
        if "県計" in info["cols"]:
            prefecture_count=as_number(ws.cell(info["flu_row"],info["cols"]["県計"]).value)

        if "県計" not in vals:
            actual_values=[]
            for key,c in info["cols"].items():
                raw_actual=ws.cell(info["flu_row"],c).value
                n_actual=as_number(raw_actual)
                actual_values.append(0.0 if n_actual is None else n_actual)

            if all(v==0.0 for v in actual_values):
                vals["県計"]=0.0
                if prefecture_count is None:
                    prefecture_count=0.0
            else:
                diagnostics.append(f"{ws.title}: 県計なし")
                continue

        region_count=sum(1 for r in REGIONS if r in info["cols"])
        if region_count < 10:
            diagnostics.append(f"{ws.title}: 地域列不足={region_count}")
            continue

        main_result={
            "prefecture":round(float(vals["県計"]),4),
            "prefecture_count":None if prefecture_count is None else round(float(prefecture_count),4),
            "regions":{k:round(float(vals.get(k,0.0)),4) for k in REGIONS if k in info["cols"]},
            "_parser":{
                "sheet":ws.title,
                "title_row":info["title_row"],
                "header_row":info["header_row"],
                "flu_row":info["flu_row"],
                "value_row":info["value_row"],
                "region_count":region_count,
                "strategy":"main_regional_table_only"
            }
        }
        break

    if main_result is None:
        raise ValueError("主表からインフルエンザ定点値を取得できません: "+"; ".join(diagnostics))

    age_result=parse_age_groups(wb, expected_total=main_result.get("prefecture_count"))

    main_result.update({
        "age_groups":age_result["age_groups"],
        "age_raw":age_result["age_raw"],
        "age_unit":age_result["age_unit"],
        "_age_parser":age_result["_age_parser"],
    })
    return main_result

def scrape_week(wp):
    soup=BeautifulSoup(get(wp.url),"html.parser")
    d1,d2=parse_dates_from_page(soup,wp.year,wp.week)

    xurl=find_excel_url(soup,wp.url)
    if not xurl:
        raise ValueError("Excelリンクが見つかりません")

    parsed=parse_influenza_excel(get(xurl,binary=True))

    topic_value=extract_topic_prefecture_value(soup)
    if topic_value is not None and abs(parsed["prefecture"]-topic_value)>0.011:
        raise ValueError(
            f"本文照合不一致: Excel={parsed['prefecture']} / 今週のトピック={topic_value}"
        )

    return {
        "year":wp.year,
        "week":wp.week,
        "start":d1.isoformat() if d1 else None,
        "end":d2.isoformat() if d2 else None,
        "label":reiwa_label(d1,d2) if d1 and d2 else f"{wp.year}-W{wp.week:02d}",
        "prefecture":parsed["prefecture"],
        "regions":parsed["regions"],
        "age_groups":parsed.get("age_groups",{}),
        "age_raw":parsed.get("age_raw",{}),
        "age_unit":parsed.get("age_unit","報告数（人）"),
        "topic":extract_topic(soup),
        "source_page":wp.url,
        "source_excel":xurl,
        "verification":{
            "method":"niigata_main_table" + ("+topic" if topic_value is not None else ""),
            "niigata_topic_value":topic_value,
            "prefecture_count":parsed.get("prefecture_count")
        },
        "_parser":parsed["_parser"],
        "_age_parser":parsed.get("_age_parser",{})
    }

def read_json(path):
    p=Path(path)
    if not p.exists():
        return {"meta":{},"weeks":[]}
    return json.loads(p.read_text(encoding="utf-8"))

def write_json(path,data):
    p=Path(path)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")

def dedupe(weeks):
    d={(w["year"],w["week"]):w for w in weeks}
    return sorted(d.values(),key=lambda x:(x["year"],x["week"]))
