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
UA = "Niigata-Infection-Radar/1.3 (public-data visualization)"
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
    out = []
    seen = set()
    for a in soup.find_all("a", href=True):
        txt = a.get_text(" ", strip=True)
        m = re.search(r"令和\s*(\d+)\s*年\s*第\s*(\d+)\s*週", txt)
        if not m:
            continue
        y = 2018 + int(m.group(1))
        w = int(m.group(2))
        if y < start_year:
            continue
        k = (y,w)
        if k not in seen:
            seen.add(k)
            out.append(WeekPage(y,w,abs_url(INDEX_URL,a["href"])))
    out.sort(key=lambda x:(x.year,x.week))
    if not out:
        raise RuntimeError("週報一覧から週ページを検出できませんでした。")
    return out

def parse_dates_from_page(soup, year, week):
    text = soup.get_text(" ", strip=True)
    m = re.search(rf"第\s*{week}\s*週.*?(\d+)月(\d+)日から.*?(\d+)月(\d+)日", text)
    if not m:
        return None, None
    sm,sd,em,ed = map(int,m.groups())
    sy = year
    ey = year + (1 if em < sm else 0)
    if week == 1 and sm == 12:
        sy = year-1
        ey = year
    try:
        return date(sy,sm,sd), date(ey,em,ed)
    except ValueError:
        return None, None

def reiwa_label(d1,d2):
    ry = d1.year - 2018
    if d1.year == d2.year:
        return f"R{ry}/{d1.month}/{d1.day}–{d2.month}/{d2.day}"
    return f"R{ry}/{d1.month}/{d1.day}–R{d2.year-2018}/{d2.month}/{d2.day}"

def extract_topic(soup):
    text = soup.get_text("\n", strip=True)
    m = re.search(
        r"◆\s*インフルエンザ([\s\S]*?)(?=\n\s*◆|\n\s*警報を発令している疾患|$)",
        text
    )
    if not m:
        return ""
    return re.sub(r"\n{3,}","\n\n","インフルエンザ"+m.group(1)).strip()[:3000]

def extract_topic_prefecture_value(soup):
    """
    今週のトピックにインフルエンザの全県値が明記されている週だけ拾う。
    例: 「インフルエンザ…全県で6.13」
    """
    topic = extract_topic(soup)
    if not topic:
        return None
    m = re.search(r"全県で\s*([0-9]+(?:\.[0-9]+)?)", topic)
    return float(m.group(1)) if m else None

def find_excel_url(soup,page_url):
    for a in soup.find_all("a",href=True):
        t = norm(a.get_text(" ",strip=True))
        href = a["href"]
        if "5類感染症定点把握対象疾患報告数" in t:
            return abs_url(page_url,href)
        if href.lower().endswith((".xlsx",".xlsm")) and "定点" in t:
            return abs_url(page_url,href)
    return None

def as_number(v):
    if isinstance(v,(int,float)) and not isinstance(v,bool):
        return float(v)
    if isinstance(v,str):
        s = v.strip().replace(",","")
        if re.fullmatch(r"-?\d+(?:\.\d+)?",s):
            return float(s)
    return None

def workbook_matrix(data):
    wb = load_workbook(io.BytesIO(data), data_only=True, read_only=False)
    for ws in wb.worksheets:
        rows = []
        for r in range(1,min(ws.max_row,500)+1):
            rows.append([ws.cell(r,c).value for c in range(1,min(ws.max_column,180)+1)])
        yield ws.title, rows

def canonical_header(s):
    s = norm(s)
    if s in ("県計","全県","県全体"):
        return "県計"
    for r in REGIONS:
        if s == r:
            return r
    return None

def locate_region_columns(rows):
    best = None
    for ri,row in enumerate(rows[:140]):
        found = {}
        for ci,v in enumerate(row):
            key = canonical_header(v)
            if key and key not in found:
                found[key] = ci
        score = len(found)
        if best is None or score > best[0]:
            best = (score,ri,found)
    return best

def is_exact_influenza_label(v):
    """
    「インフルエンザ/COVID-19定点」等の一般ラベルを除外し、
    疾患名としてのインフルエンザだけを許可。
    """
    s = norm(v)
    if not s:
        return False
    if s == "インフルエンザ":
        return True
    # 注記付きだけは許可
    if re.fullmatch(r"インフルエンザ[（(][^）)]{0,20}[）)]", s):
        return True
    return False

def find_influenza_rows(rows):
    hits = []
    for ri,row in enumerate(rows):
        # 疾患名は通常左側にあるので先頭12列だけを見る
        for ci,v in enumerate(row[:12]):
            if is_exact_influenza_label(v):
                hits.append((ri,ci))
                break
    return hits

def parse_influenza_excel(data):
    best = None
    diagnostics = []

    for sheet,rows in workbook_matrix(data):
        hdr = locate_region_columns(rows)
        if not hdr or hdr[0] < 10:
            diagnostics.append(f"{sheet}: 地域見出し不足")
            continue

        _,hrow,cols = hdr
        flu_hits = find_influenza_rows(rows)
        if not flu_hits:
            diagnostics.append(f"{sheet}: 疾患名『インフルエンザ』の完全一致行なし")
            continue

        first_region_col = min(cols.values())

        for fr, disease_col in flu_hits:
            # 疾患名行の直後だけを見る。
            # 他疾患ブロックへ跨がないよう最大4行。
            for rr in range(fr, min(len(rows), fr+5)):
                row = rows[rr]

                # rr > fr で次の疾患名が出たらそこで打ち切り
                if rr > fr and any(
                    isinstance(v,str) and
                    norm(v) not in ("","定点当","実数") and
                    (
                        "新型コロナウイルス" in norm(v)
                        or "RSウイルス" in norm(v)
                        or "咽頭結膜熱" in norm(v)
                        or "A群溶血性" in norm(v)
                        or "感染性胃腸炎" in norm(v)
                        or "水痘" in norm(v)
                        or "手足口病" in norm(v)
                    )
                    for v in row[:12]
                ):
                    break

                left_text = "".join(norm(x) for x in row[:first_region_col] if x is not None)

                # 定点当行以外は候補にしない
                if "定点当" not in left_text:
                    continue
                if "実数" in left_text:
                    continue

                vals = {}
                for k,c in cols.items():
                    if c < len(row):
                        n = as_number(row[c])
                        if n is not None:
                            vals[k] = n

                # 県計必須 + 地域は最低10区分
                if "県計" not in vals:
                    continue
                region_count = sum(1 for k in REGIONS if k in vals)
                if region_count < 10:
                    continue

                rec = {
                    "sheet": sheet,
                    "header_row": hrow+1,
                    "flu_row": fr+1,
                    "value_row": rr+1,
                    "prefix": left_text,
                    "region_count": region_count,
                    "score": 100 + region_count,
                    "values": vals
                }
                if best is None or rec["score"] > best["score"]:
                    best = rec

    if not best:
        raise ValueError(
            "インフルエンザ疾患ブロック内の『定点当』行を特定できません: "
            + "; ".join(diagnostics)
        )

    vals = best["values"]
    return {
        "prefecture": round(float(vals["県計"]),4),
        "regions": {k:round(float(vals[k]),4) for k in REGIONS if k in vals},
        "_parser": {k:v for k,v in best.items() if k!="values"}
    }

def scrape_week(wp):
    soup = BeautifulSoup(get(wp.url),"html.parser")
    d1,d2 = parse_dates_from_page(soup,wp.year,wp.week)
    xurl = find_excel_url(soup,wp.url)
    if not xurl:
        raise ValueError("Excelリンクが見つかりません")

    parsed = parse_influenza_excel(get(xurl,binary=True))

    # 県ページ本文にインフルエンザの全県値がある週は照合する。
    page_value = extract_topic_prefecture_value(soup)
    if page_value is not None and abs(parsed["prefecture"] - page_value) > 0.011:
        raise ValueError(
            f"本文照合不一致: Excel={parsed['prefecture']} / 今週のトピック={page_value}"
        )

    return {
        "year": wp.year,
        "week": wp.week,
        "start": d1.isoformat() if d1 else None,
        "end": d2.isoformat() if d2 else None,
        "label": reiwa_label(d1,d2) if d1 and d2 else f"{wp.year}-W{wp.week:02d}",
        "prefecture": parsed["prefecture"],
        "regions": parsed["regions"],
        "topic": extract_topic(soup),
        "source_page": wp.url,
        "source_excel": xurl,
        "_parser": parsed["_parser"]
    }

def read_json(path):
    p = Path(path)
    if not p.exists():
        return {"meta":{},"weeks":[]}
    return json.loads(p.read_text(encoding="utf-8"))

def write_json(path,data):
    p = Path(path)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")

def dedupe(weeks):
    d = {(w["year"],w["week"]):w for w in weeks}
    return sorted(d.values(),key=lambda x:(x["year"],x["week"]))
