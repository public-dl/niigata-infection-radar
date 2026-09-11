from __future__ import annotations
import io, json, re, time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any
import requests
from bs4 import BeautifulSoup
from openpyxl import load_workbook

INDEX_URL = "https://www.pref.niigata.lg.jp/sec/kanyaku/1232482573101.html"
UA = "Niigata-Infection-Radar/1.0 (public-data visualization)"
REGIONS = ["新潟市","新発田","新津","三条","長岡","魚沼","南魚沼","十日町","柏崎","糸魚川","村上","佐渡","上越"]
ALL_KEYS = ["全県"] + REGIONS

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA})

def norm(v: Any) -> str:
    if v is None: return ""
    s = str(v).replace("\u3000"," ").replace("\n"," ").replace("\r"," ")
    return re.sub(r"\s+", "", s)

def get(url: str, binary=False):
    r = SESSION.get(url, timeout=35)
    r.raise_for_status()
    return r.content if binary else r.text

def abs_url(base: str, href: str) -> str:
    from urllib.parse import urljoin
    return urljoin(base, href)

@dataclass
class WeekPage:
    year: int
    week: int
    url: str

def discover_week_pages(start_year=2025) -> list[WeekPage]:
    soup = BeautifulSoup(get(INDEX_URL), "html.parser")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        txt = a.get_text(" ", strip=True)
        m = re.search(r"令和(\d+)年第(\d+)週", txt)
        if not m: continue
        y = 2018 + int(m.group(1))
        w = int(m.group(2))
        if y < start_year: continue
        u = abs_url(INDEX_URL, a["href"])
        k=(y,w)
        if k not in seen:
            seen.add(k); out.append(WeekPage(y,w,u))
    return sorted(out, key=lambda x:(x.year,x.week))

def parse_dates_from_page(soup: BeautifulSoup, gregorian_year: int, week: int):
    text = soup.get_text(" ", strip=True)
    m = re.search(r"第\s*%d\s*週[：:]\s*(\d+)月(\d+)日から(?:\s*令和\d+年)?\s*(\d+)月(\d+)日" % week, text)
    if not m:
        # index/page wording can contain "まで"
        m = re.search(r"第\s*%d\s*週.*?(\d+)月(\d+)日から.*?(\d+)月(\d+)日" % week, text)
    if not m: return None, None
    sm, sd, em, ed = map(int, m.groups())
    sy = gregorian_year
    ey = gregorian_year + (1 if em < sm else 0)
    # first epidemiological week may begin in previous calendar year
    if week == 1 and sm == 12:
        sy = gregorian_year - 1
        ey = gregorian_year
    try:
        return date(sy,sm,sd), date(ey,em,ed)
    except ValueError:
        return None, None

def reiwa_label(d1: date, d2: date) -> str:
    ry = d1.year - 2018
    if d1.year == d2.year:
        return f"R{ry}/{d1.month}/{d1.day}–{d2.month}/{d2.day}"
    return f"R{ry}/{d1.month}/{d1.day}–R{d2.year-2018}/{d2.month}/{d2.day}"

def extract_topic(soup: BeautifulSoup) -> str:
    # Preserve text from the "influenza" bullet until the next ◆ / next section.
    text = soup.get_text("\n", strip=True)
    m = re.search(r"◆\s*インフルエンザ([\s\S]*?)(?=\n\s*◆|\n\s*###|\n\s*警報を発令している疾患|$)", text)
    if not m:
        return ""
    block = "インフルエンザ" + m.group(1)
    block = re.sub(r"\n{3,}", "\n\n", block).strip()
    return block[:3000]

def find_excel_url(soup: BeautifulSoup, page_url: str) -> str | None:
    for a in soup.find_all("a", href=True):
        t = norm(a.get_text(" ", strip=True))
        if "5類感染症定点把握対象疾患報告数" in t or ("Excel" in t and "定点" in t):
            return abs_url(page_url, a["href"])
    return None

def as_number(v):
    if isinstance(v, (int,float)) and not isinstance(v,bool): return float(v)
    if isinstance(v,str):
        s=v.strip().replace(",","")
        if re.fullmatch(r"-?\d+(?:\.\d+)?", s):
            return float(s)
    return None

def workbook_matrix(xlsx_bytes: bytes):
    wb = load_workbook(io.BytesIO(xlsx_bytes), data_only=True, read_only=False)
    for ws in wb.worksheets:
        rows = []
        max_col = min(ws.max_column, 180)
        max_row = min(ws.max_row, 500)
        for r in range(1,max_row+1):
            rows.append([ws.cell(r,c).value for c in range(1,max_col+1)])
        yield ws.title, rows

def locate_region_columns(rows):
    best = None
    for ri,row in enumerate(rows[:120]):
        nr=[norm(x) for x in row]
        found={}
        for key in ALL_KEYS:
            for ci,s in enumerate(nr):
                if s == key or (key=="全県" and s in ("全県","県全体")):
                    found[key]=ci; break
        score=len(found)
        if best is None or score>best[0]:
            best=(score,ri,found)
    return best

def score_candidate_row(row, region_cols):
    nums=0
    vals={}
    for k,c in region_cols.items():
        if c < len(row):
            n=as_number(row[c])
            if n is not None:
                nums += 1; vals[k]=n
    prefix="".join(norm(x) for x in row[:min(region_cols.values())] if x is not None)
    bonus = 4 if "定点当たり" in prefix else 0
    penalty = 2 if "報告数" in prefix and "定点当たり" not in prefix else 0
    return nums + bonus - penalty, vals, prefix

def parse_influenza_excel(xlsx_bytes: bytes):
    diagnostics=[]
    best_result=None
    for sheet,rows in workbook_matrix(xlsx_bytes):
        header=locate_region_columns(rows)
        if not header or header[0] < 5:
            diagnostics.append(f"{sheet}: 地域見出し不足 ({header[0] if header else 0})")
            continue
        _,hrow,cols=header
        flu_rows=[]
        for ri,row in enumerate(rows):
            if any("インフルエンザ" in norm(v) for v in row):
                flu_rows.append(ri)
        if not flu_rows:
            diagnostics.append(f"{sheet}: インフルエンザ行なし")
            continue

        for fr in flu_rows:
            for rr in range(max(0,fr-2), min(len(rows),fr+6)):
                score,vals,prefix=score_candidate_row(rows[rr],cols)
                if "定点当たり" in prefix: score += 6
                # realistic range safeguard, but do not discard large outbreak values
                if "全県" in vals and 0 <= vals["全県"] <= 500: score += 2
                rec={"sheet":sheet,"header_row":hrow+1,"flu_row":fr+1,"value_row":rr+1,
                     "score":score,"values":vals,"prefix":prefix}
                if best_result is None or score>best_result["score"]:
                    best_result=rec

    if not best_result or "全県" not in best_result["values"]:
        raise ValueError("Excelからインフルエンザ定点値を特定できません: "+"; ".join(diagnostics))

    vals=best_result["values"]
    # Keep only expected keys and JSON-friendly values.
    return {
      "prefecture": round(float(vals["全県"]), 4),
      "regions": {k:round(float(vals[k]),4) for k in REGIONS if k in vals},
      "_parser": {k:v for k,v in best_result.items() if k!="values"}
    }

def scrape_week(wp: WeekPage):
    html=get(wp.url)
    soup=BeautifulSoup(html,"html.parser")
    d1,d2=parse_dates_from_page(soup, wp.year, wp.week)
    xurl=find_excel_url(soup, wp.url)
    if not xurl: raise ValueError("Excelリンクが見つかりません")
    xb=get(xurl,binary=True)
    parsed=parse_influenza_excel(xb)
    out={
      "year":wp.year,"week":wp.week,
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
    return out

def read_json(path: Path):
    if not path.exists(): return {"meta":{}, "weeks":[]}
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path: Path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")

def sort_weeks(weeks):
    return sorted(weeks,key=lambda x:(x.get("year",0),x.get("week",0)))

def dedupe(weeks):
    d={}
    for w in weeks: d[(w["year"],w["week"])]=w
    return sort_weeks(list(d.values()))
