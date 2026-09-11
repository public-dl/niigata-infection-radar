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
UA = "Niigata-Infection-Radar/1.5 (public-data visualization)"
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
    try:
        return r.content.decode("utf-8")
    except UnicodeDecodeError:
        return r.content.decode(r.apparent_encoding or "cp932", errors="replace")

def abs_url(base, href):
    from urllib.parse import urljoin
    return urljoin(base, href)

@dataclass
class WeekPage:
    year:int
    week:int
    url:str

def discover_week_pages(start_year=2025):
    soup = BeautifulSoup(get(INDEX_URL), "html.parser")
    out=[]; seen=set()
    for a in soup.find_all("a", href=True):
        txt=a.get_text(" ",strip=True)
        m=re.search(r"令和\s*(\d+)\s*年\s*第\s*(\d+)\s*週",txt)
        if not m:
            continue
        y=2018+int(m.group(1)); w=int(m.group(2))
        if y<start_year:
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

def workbook_matrix(data):
    wb=load_workbook(io.BytesIO(data),data_only=True,read_only=False)
    for ws in wb.worksheets:
        rows=[]
        for r in range(1,min(ws.max_row,500)+1):
            rows.append([ws.cell(r,c).value for c in range(1,min(ws.max_column,180)+1)])
        yield ws.title,rows

def canonical_header(s):
    s=norm(s)
    if s in ("県計","全県","県全体"):
        return "県計"
    for r in REGIONS:
        if s==r:
            return r
    return None

def locate_region_columns(rows):
    best=None
    for ri,row in enumerate(rows[:160]):
        found={}
        for ci,v in enumerate(row):
            key=canonical_header(v)
            if key and key not in found:
                found[key]=ci
        score=len(found)
        if best is None or score>best[0]:
            best=(score,ri,found)
    return best

def is_influenza_label(v):
    s=norm(v)
    if not s:
        return False

    if s=="インフルエンザ":
        return True

    # 長い正式名称は許可
    if s.startswith("インフルエンザ（") or s.startswith("インフルエンザ("):
        if any(x in s for x in ("定点","COVID","新型コロナ")):
            return False
        return True

    return False

def collect_influenza_candidates(data):
    """
    Excel内に複数の「インフルエンザ」表がある週があるため、
    まず候補をすべて集める。
    """
    candidates=[]
    diagnostics=[]

    for sheet,rows in workbook_matrix(data):
        hdr=locate_region_columns(rows)
        if not hdr or hdr[0] < 5:
            diagnostics.append(f"{sheet}: 地域見出し不足")
            continue

        _,hrow,cols=hdr
        first_region_col=min(cols.values())

        flu_rows=[]
        for ri,row in enumerate(rows):
            if any(is_influenza_label(v) for v in row[:20]):
                flu_rows.append(ri)

        if not flu_rows:
            diagnostics.append(f"{sheet}: インフルエンザ行なし")
            continue

        for fr in flu_rows:
            # 疾患行の近傍だけ確認。
            # 旧レイアウトでは数行離れていることがあるため +8。
            for rr in range(fr, min(len(rows), fr+9)):
                row=rows[rr]
                left_text="".join(norm(x) for x in row[:first_region_col] if x is not None)

                if "定点当" not in left_text:
                    continue
                if "実数" in left_text:
                    continue

                vals={}
                for k,c in cols.items():
                    if c < len(row):
                        n=as_number(row[c])
                        if n is not None:
                            vals[k]=n

                if "県計" not in vals:
                    continue

                region_count=sum(1 for k in REGIONS if k in vals)
                if region_count < 10:
                    continue

                candidates.append({
                    "sheet":sheet,
                    "header_row":hrow+1,
                    "flu_row":fr+1,
                    "value_row":rr+1,
                    "prefix":left_text,
                    "region_count":region_count,
                    "score":100+region_count,
                    "values":vals
                })

    return candidates, diagnostics

def parse_influenza_excel(data, expected_prefecture=None):
    candidates, diagnostics = collect_influenza_candidates(data)

    if not candidates:
        raise ValueError(
            "インフルエンザ定点候補を特定できません: "
            + "; ".join(diagnostics)
        )

    # 県ページ本文に正解値が明記されている週は、その値と一致する候補を最優先。
    if expected_prefecture is not None:
        matched=[
            c for c in candidates
            if abs(float(c["values"]["県計"]) - float(expected_prefecture)) <= 0.011
        ]
        if matched:
            matched.sort(key=lambda c:(c["region_count"], -c["value_row"]), reverse=True)
            best=matched[0]
        else:
            vals=sorted(set(round(float(c["values"]["県計"]),4) for c in candidates))
            raise ValueError(
                f"本文値 {expected_prefecture} に一致するインフルエンザ候補がありません。"
                f" Excel候補={vals}"
            )
    else:
        # 本文に値がない週は、地域数が最も揃う候補を優先。
        # 同点ならシート上で先に出るものを採用。
        candidates.sort(key=lambda c:(-c["region_count"], c["value_row"]))
        best=candidates[0]

    vals=best["values"]
    return {
        "prefecture":round(float(vals["県計"]),4),
        "regions":{k:round(float(vals[k]),4) for k in REGIONS if k in vals},
        "_parser":{k:v for k,v in best.items() if k!="values"}
    }

def scrape_week(wp):
    soup=BeautifulSoup(get(wp.url),"html.parser")
    d1,d2=parse_dates_from_page(soup,wp.year,wp.week)
    xurl=find_excel_url(soup,wp.url)
    if not xurl:
        raise ValueError("Excelリンクが見つかりません")

    page_value=extract_topic_prefecture_value(soup)
    parsed=parse_influenza_excel(
        get(xurl,binary=True),
        expected_prefecture=page_value
    )

    # 念のため再照合
    if page_value is not None and abs(parsed["prefecture"]-page_value)>0.011:
        raise ValueError(
            f"本文照合不一致: Excel={parsed['prefecture']} / 今週のトピック={page_value}"
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
