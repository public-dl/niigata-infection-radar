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
UA = "Niigata-Infection-Radar/2.0 (public-data visualization)"
REGIONS = ["新潟市","新発田","新津","三条","長岡","魚沼","南魚沼","十日町","柏崎","糸魚川","村上","佐渡","上越"]

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

    # タイトル直後3行以内に地域見出し行がある
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

    # 地域見出しの直後10行以内で、A列にインフルエンザ
    flu_row=None
    for r in range(header_row+1, min(ws.max_row, header_row+12)+1):
        if norm(ws.cell(r,1).value) == "インフルエンザ":
            flu_row=r
            break

    if flu_row is None:
        return None

    # 直後3行以内の「定点当」行
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

def parse_influenza_excel(data):
    wb=load_workbook(io.BytesIO(data),data_only=True,read_only=False)
    diagnostics=[]

    for ws in wb.worksheets:
        info=find_main_table(ws)
        if not info:
            diagnostics.append(f"{ws.title}: 主表を特定できず")
            continue

        vals={}
        for key,c in info["cols"].items():
            raw = ws.cell(info["value_row"],c).value
            n = as_number(raw)
            # 地域別表の空欄は「報告なし」= 0 と扱う。
            # 県計だけは空欄なら異常として扱う。
            if key == "県計":
                if n is not None:
                    vals[key]=n
            else:
                vals[key]=0.0 if n is None else n

        if "県計" not in vals:
            # 県計セルが空欄でも、インフルエンザ実数行が全地域で
            # 空欄または0なら「報告なし」= 0.0 と判断する。
            actual_values = []
            for key, c in info["cols"].items():
                raw_actual = ws.cell(info["flu_row"], c).value
                n_actual = as_number(raw_actual)
                actual_values.append(0.0 if n_actual is None else n_actual)

            if all(v == 0.0 for v in actual_values):
                vals["県計"] = 0.0
            else:
                diagnostics.append(f"{ws.title}: 県計なし")
                continue

        region_count=sum(1 for r in REGIONS if r in info["cols"])
        if region_count < 10:
            diagnostics.append(f"{ws.title}: 地域列不足={region_count}")
            continue

        return {
            "prefecture":round(float(vals["県計"]),4),
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

    raise ValueError("主表からインフルエンザ定点値を取得できません: "+"; ".join(diagnostics))

def scrape_week(wp):
    soup=BeautifulSoup(get(wp.url),"html.parser")
    d1,d2=parse_dates_from_page(soup,wp.year,wp.week)

    xurl=find_excel_url(soup,wp.url)
    if not xurl:
        raise ValueError("Excelリンクが見つかりません")

    parsed=parse_influenza_excel(get(xurl,binary=True))

    # 本文にインフルエンザ県計がある週だけ照合
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
        "topic":extract_topic(soup),
        "source_page":wp.url,
        "source_excel":xurl,
        "verification":{
            "method":"niigata_main_table" + ("+topic" if topic_value is not None else ""),
            "niigata_topic_value":topic_value
        },
        "_parser":parsed["_parser"]
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
