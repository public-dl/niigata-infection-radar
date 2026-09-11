from __future__ import annotations
import io, json, re, time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
import requests
from bs4 import BeautifulSoup
from openpyxl import load_workbook

INDEX_URL = "https://www.pref.niigata.lg.jp/sec/kanyaku/1232482573101.html"
UA = "Niigata-Infection-Radar/1.1 (public-data visualization)"
REGIONS = ["新潟市","新発田","新津","三条","長岡","魚沼","南魚沼","十日町","柏崎","糸魚川","村上","佐渡","上越"]
ALL_KEYS = ["全県"] + REGIONS

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": UA,
    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
})

def norm(v: Any) -> str:
    if v is None: return ""
    s = str(v).replace("\u3000"," ").replace("\n"," ").replace("\r"," ")
    return re.sub(r"\s+", "", s)

def get(url: str, binary=False):
    r = SESSION.get(url, timeout=35)
    r.raise_for_status()
    if binary:
        return r.content

    # 新潟県サイトは requests が文字コードを誤判定する場合があるため、
    # HTML はまず UTF-8 として明示的に読む。
    raw = r.content
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        enc = r.apparent_encoding or "cp932"
        return raw.decode(enc, errors="replace")

def abs_url(base: str, href: str) -> str:
    from urllib.parse import urljoin
    return urljoin(base, href)

@dataclass
class WeekPage:
    year: int
    week: int
    url: str

def discover_week_pages(start_year=2025) -> list[WeekPage]:
    html = get(INDEX_URL)
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()

    for a in soup.find_all("a", href=True):
        txt = a.get_text(" ", strip=True)
        # 例:
        # 新潟県感染症週報（週報速報版） 令和8年第36週分（8月31日から9月6日まで）
        m = re.search(r"令和\s*(\d+)\s*年\s*第\s*(\d+)\s*週", txt)
        if not m:
            continue
        y = 2018 + int(m.group(1))
        w = int(m.group(2))
        if y < start_year:
            continue
        u = abs_url(INDEX_URL, a["href"])
        k = (y, w)
        if k not in seen:
            seen.add(k)
            out.append(WeekPage(y, w, u))

    out = sorted(out, key=lambda x: (x.year, x.week))
    if not out:
        # 緑チェックなのに0件、を防止するため明示的に失敗させる。
        sample = soup.get_text(" ", strip=True)[:500]
        raise RuntimeError(
            "週報一覧から週ページを1件も検出できませんでした。"
            "HTMLの文字コードまたはページ構造が変更された可能性があります。"
            f" sample={sample!r}"
        )
    return out

def parse_dates_from_page(soup: BeautifulSoup, gregorian_year: int, week: int):
    text = soup.get_text(" ", strip=True)
    # 令和8年第36週：8月31日から9月6日まで
    m = re.search(
        rf"第\s*{week}\s*週[^0-9]*(?:(?:令和\s*\d+\s*年)?\s*)"
        r"(\d+)月(\d+)日から(?:(?:\s*令和\s*\d+\s*年)?\s*)(\d+)月(\d+)日",
        text
    )
    if not m:
        return None, None
    sm, sd, em, ed = map(int, m.groups())
    sy = gregorian_year
    ey = gregorian_year + (1 if em < sm else 0)
    if week == 1 and sm == 12:
        sy = gregorian_year - 1
        ey = gregorian_year
    try:
        return date(sy, sm, sd), date(ey, em, ed)
    except ValueError:
        return None, None

def reiwa_label(d1: date, d2: date) -> str:
    ry = d1.year - 2018
    if d1.year == d2.year:
        return f"R{ry}/{d1.month}/{d1.day}–{d2.month}/{d2.day}"
    return f"R{ry}/{d1.month}/{d1.day}–R{d2.year-2018}/{d2.month}/{d2.day}"

def extract_topic(soup: BeautifulSoup) -> str:
    text = soup.get_text("\n", strip=True)
    m = re.search(
        r"◆\s*インフルエンザ([\s\S]*?)(?=\n\s*◆|\n\s*警報を発令している疾患|$)",
        text
    )
    if not m:
        return ""
    block = "インフルエンザ" + m.group(1)
    block = re.sub(r"\n{3,}", "\n\n", block).strip()
    return block[:3000]

def find_excel_url(soup: BeautifulSoup, page_url: str) -> str | None:
    for a in soup.find_all("a", href=True):
        t = norm(a.get_text(" ", strip=True))
        href = a["href"]
        if "5類感染症定点把握対象疾患報告数" in t:
            return abs_url(page_url, href)
        if ("Excel" in t or href.lower().endswith((".xlsx",".xlsm",".xls"))) and "定点" in t:
            return abs_url(page_url, href)
    return None

def as_number(v):
    if isinstance(v, (int,float)) and not isinstance(v,bool):
        return float(v)
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
        for r in range(1, max_row+1):
            rows.append([ws.cell(r,c).value for c in range(1,max_col+1)])
        yield ws.title, rows

def locate_region_columns(rows):
    best = None
    for ri,row in enumerate(rows[:140]):
        nr=[norm(x) for x in row]
        found={}
        for key in ALL_KEYS:
            for ci,s in enumerate(nr):
                if s == key or (key=="全県" and s in ("全県","県全体")):
                    found[key]=ci
                    break
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
                nums += 1
                vals[k]=n
    first_col = min(region_cols.values()) if region_cols else 0
    prefix="".join(norm(x) for x in row[:first_col] if x is not None)
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
            for rr in range(max(0,fr-3), min(len(rows),fr+8)):
                score,vals,prefix=score_candidate_row(rows[rr],cols)
                if "定点当たり" in prefix:
                    score += 8
                if "全県" in vals and 0 <= vals["全県"] <= 500:
                    score += 2
                rec={
                    "sheet":sheet,
                    "header_row":hrow+1,
                    "flu_row":fr+1,
                    "value_row":rr+1,
                    "score":score,
                    "values":vals,
                    "prefix":prefix
                }
                if best_result is None or score>best_result["score"]:
                    best_result=rec

    if not best_result or "全県" not in best_result["values"]:
        raise ValueError(
            "Excelからインフルエンザ定点値を特定できません: "
            + "; ".join(diagnostics)
        )

    vals=best_result["values"]
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
    if not xurl:
        raise ValueError("Excelリンクが見つかりません")
    xb=get(xurl,binary=True)
    parsed=parse_influenza_excel(xb)
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

def read_json(path: Path):
    if not path.exists():
        return {"meta":{}, "weeks":[]}
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path: Path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")

def sort_weeks(weeks):
    return sorted(weeks,key=lambda x:(x.get("year",0),x.get("week",0)))

def dedupe(weeks):
    d={}
    for w in weeks:
        d[(w["year"],w["week"])]=w
    return sort_weeks(list(d.values()))
