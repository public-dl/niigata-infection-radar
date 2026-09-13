#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import math
import os
import re
import urllib.request
from pathlib import Path

from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.utils import ImageReader

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "influenza_history.json"
AI_PATH = ROOT / "data" / "ai_comment.json"
REPORT_DIR = ROOT / "reports"
ASSET_DIR = ROOT / ".report_assets"
QR_PATH = ROOT / "assets" / "qr-niigata-influenza-radar.png"

GEO_URL = (
    "https://raw.githubusercontent.com/smartnews-smri/japan-topography/"
    "refs/heads/main/data/municipality/geojson/s0010/N03-21_15_210101.json"
)

REGION_MUNICIPALITIES = {
    "村上": ["村上市", "関川村", "粟島浦村"],
    "新発田": ["新発田市", "阿賀野市", "胎内市", "聖籠町"],
    "新潟市": ["新潟市"],
    "新津": ["五泉市", "阿賀町"],
    "三条": ["三条市", "加茂市", "燕市", "弥彦村", "田上町"],
    "長岡": ["長岡市", "小千谷市", "見附市", "出雲崎町"],
    "魚沼": ["魚沼市"],
    "南魚沼": ["南魚沼市", "湯沢町"],
    "十日町": ["十日町市", "津南町"],
    "柏崎": ["柏崎市", "刈羽村"],
    "上越": ["上越市", "妙高市"],
    "糸魚川": ["糸魚川市"],
    "佐渡": ["佐渡市"],
}
MUNI_TO_REGION = {
    m: r for r, munis in REGION_MUNICIPALITIES.items() for m in munis
}

BLUE = "#0b79b6"
YELLOW = "#f2c94c"
RED = "#ef6a5b"
PURPLE = "#7b4bb7"

def tier_color(v: float) -> str:
    if v >= 30:
        return PURPLE
    if v >= 10:
        return RED
    if v >= 1:
        return YELLOW
    return BLUE

def region_for_feature(p: dict) -> str | None:
    # Designated-city wards should roll up to 新潟市.
    if p.get("N03_003") == "新潟市":
        return "新潟市"
    candidates = [
        p.get("N03_004"),
        p.get("N03_003"),
        p.get("N03_002"),
    ]
    for name in candidates:
        if name in MUNI_TO_REGION:
            return MUNI_TO_REGION[name]
    return None

def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def weeks_sorted(history: dict):
    return sorted(history.get("weeks", []), key=lambda w: (int(w["year"]), int(w["week"])))

def download_geojson() -> dict:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    cache = ASSET_DIR / "niigata_municipalities.geojson"
    if not cache.exists():
        with urllib.request.urlopen(GEO_URL, timeout=30) as r:
            cache.write_bytes(r.read())
    return load_json(cache)

def polygon_rings(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    if geom["type"] == "MultiPolygon":
        return [poly[0] for poly in geom["coordinates"]]
    return []

def make_map(latest: dict, out: Path):
    geo = download_geojson()
    regions = latest.get("regions") or {}

    fig, ax = plt.subplots(figsize=(8.3, 4.0), dpi=160)
    ax.set_facecolor("#edf6fb")
    fig.patch.set_facecolor("white")

    all_x, all_y = [], []
    for f in geo.get("features", []):
        p = f.get("properties") or {}
        region = region_for_feature(p)
        val = float(regions.get(region, 0) or 0)
        color = tier_color(val)
        for ring in polygon_rings(f["geometry"]):
            pts = [(float(x), float(y)) for x, y in ring]
            if len(pts) < 3:
                continue
            all_x.extend(x for x, _ in pts)
            all_y.extend(y for _, y in pts)
            ax.add_patch(
                MplPolygon(
                    pts, closed=True,
                    facecolor=color,
                    edgecolor="white",
                    linewidth=0.35
                )
            )
    if all_x:
        padx = (max(all_x) - min(all_x)) * 0.03
        pady = (max(all_y) - min(all_y)) * 0.03
        ax.set_xlim(min(all_x)-padx, max(all_x)+padx)
        ax.set_ylim(min(all_y)-pady, max(all_y)+pady)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    fig.tight_layout(pad=0.05)
    fig.savefig(out, bbox_inches="tight", pad_inches=0.02, facecolor="white")
    plt.close(fig)

def make_trend(weeks: list[dict], latest: dict, out: Path):
    current = weeks[-13:]
    labels = [w.get("label","") for w in current]
    vals = [float(w.get("prefecture") or 0) for w in current]
    prev_vals = []
    for w in current:
        prev = next(
            (x for x in weeks if int(x["year"]) == int(w["year"])-1 and int(x["week"]) == int(w["week"])),
            None,
        )
        prev_vals.append(None if prev is None else float(prev.get("prefecture") or 0))

    x = list(range(len(current)))
    fig, ax = plt.subplots(figsize=(7.4, 3.5), dpi=160)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f7fbfd")
    ax.plot(x, vals, color=BLUE, linewidth=2.6, marker="o", markersize=3.5, label=f"{latest['year']}")
    ax.fill_between(x, vals, color=BLUE, alpha=0.08)
    if any(v is not None for v in prev_vals):
        ax.plot(x, prev_vals, color="#8fa3b1", linewidth=1.9, linestyle="--", label="前年同期")
    for y, c, t in [(1, YELLOW, "1"), (10, RED, "10"), (30, PURPLE, "30")]:
        ax.axhline(y, color=c, linewidth=0.9, alpha=0.55)
    ax.grid(axis="y", color="#dfeaf0", linewidth=0.7)
    ax.set_xticks(x[::2])
    ax.set_xticklabels([labels[i] for i in x[::2]], fontsize=7, rotation=0)
    ax.tick_params(axis="y", labelsize=7)
    ax.spines[["top","right","left"]].set_visible(False)
    ax.spines["bottom"].set_color("#cedde6")
    ax.legend(loc="upper left", frameon=False, fontsize=7)
    fig.tight_layout(pad=0.7)
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)

pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
FONT = "HeiseiKakuGo-W5"

def wrap_ja(c, text, max_width, font=FONT, size=8):
    lines = []
    cur = ""
    for ch in text:
        test = cur + ch
        if c.stringWidth(test, font, size) > max_width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines

def draw_img_fit(c, path: Path, x, y, w, h):
    img = Image.open(path).convert("RGB")
    iw, ih = img.size
    scale = min(w/iw, h/ih)
    nw, nh = iw*scale, ih*scale
    c.drawImage(ImageReader(img), x+(w-nw)/2, y+(h-nh)/2, width=nw, height=nh, mask="auto")

def build_report(history: dict, ai: dict):
    weeks = weeks_sorted(history)
    latest = weeks[-1]
    prev = weeks[-2] if len(weeks) > 1 else None
    prev2 = weeks[-3] if len(weeks) > 2 else None

    src = ai.get("source_week") or {}
    if int(src.get("year", -1)) != int(latest["year"]) or int(src.get("week", -1)) != int(latest["week"]):
        raise RuntimeError("ai_comment.json が influenza_history.json の最新週と一致しません。")

    REPORT_DIR.mkdir(exist_ok=True)
    ASSET_DIR.mkdir(exist_ok=True)
    map_png = ASSET_DIR / "latest_map.png"
    trend_png = ASSET_DIR / "latest_trend.png"
    make_map(latest, map_png)
    make_trend(weeks, latest, trend_png)

    latest_name = REPORT_DIR / "latest.pdf"
    dated_name = REPORT_DIR / f"niigata_influenza_report_{latest['year']}W{int(latest['week']):02d}.pdf"

    W, H = landscape(A4)
    c = canvas.Canvas(str(dated_name), pagesize=(W, H))
    NAVY = HexColor("#103F67")
    TEXT = HexColor("#18394F")
    MUTED = HexColor("#688090")
    LINE = HexColor("#D8E7F0")
    WHITE = HexColor("#FFFFFF")
    BG = HexColor("#EDF4F8")

    def txt(x, y, s, size=8, color=TEXT):
        c.setFillColor(color)
        c.setFont(FONT, size)
        c.drawString(x, y, str(s))

    def right(x, y, s, size=8, color=TEXT):
        c.setFillColor(color)
        c.setFont(FONT, size)
        c.drawRightString(x, y, str(s))

    def card(x, y, w, h, r=10):
        c.setFillColor(WHITE)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.6)
        c.roundRect(x, y, w, h, r, fill=1, stroke=1)

    c.setFillColor(BG)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # Header
    c.setFillColor(WHITE)
    c.rect(0, H-54, W, 54, fill=1, stroke=0)
    txt(22, H-27, "インフルエンザレポート（新潟県）", 16, NAVY)
    txt(22, H-42, "NIIGATA INFLUENZA WEEKLY REPORT", 7, MUTED)
    right(W-22, H-27, f"{latest['year']} 第{latest['week']}週（{latest.get('label','')}）", 10.5, NAVY)
    right(W-22, H-42, "データ出典：新潟県 感染症情報（週報）", 6.8, MUTED)

    # Top metrics
    top_y = H-68
    card(22, top_y-92, 205, 92)
    txt(35, top_y-18, "県全体・定点当たり報告数", 7.2, MUTED)
    val = float(latest.get("prefecture") or 0)
    txt(35, top_y-57, f"{val:.2f}", 29, HexColor(tier_color(val)))
    txt(123, top_y-54, "人／定点", 7.5, MUTED)
    for i,(lab,w) in enumerate([("前週",prev),("前々週",prev2)]):
        if w:
            txt(35+i*78, top_y-78, lab, 6.2, MUTED)
            txt(70+i*78, top_y-78, f"{float(w.get('prefecture') or 0):.2f}", 8.6, NAVY)

    # AI insight - same ai_comment.json as web
    ix, iw = 239, W-261
    card(ix, top_y-92, iw, 92)
    txt(ix+14, top_y-17, "AI WEEKLY INSIGHT", 7.0, HexColor(BLUE))
    txt(ix+14, top_y-34, ai.get("headline","今週の流行分析"), 11.5, NAVY)

    insight_text = " ".join([
        ai.get("summary",""),
        ai.get("trend",""),
        ai.get("regional",""),
        ai.get("year_on_year",""),
    ]).strip()
    lines = wrap_ja(c, insight_text, iw-28, size=7.2)
    for j, line in enumerate(lines[:4]):
        txt(ix+14, top_y-50-j*10.5, line, 7.2, TEXT)

    # Middle panels
    mid_y, panel_h = 206, 214
    map_x, map_w = 22, 478
    trend_x, trend_w = 512, W-534
    card(map_x, mid_y, map_w, panel_h)
    txt(map_x+14, mid_y+panel_h-18, "AREA MAP", 6.8, HexColor(BLUE))
    txt(map_x+14, mid_y+panel_h-35, "地域別の流行状況", 11.5, NAVY)
    draw_img_fit(c, map_png, map_x+10, mid_y+10, map_w-20, panel_h-52)

    card(trend_x, mid_y, trend_w, panel_h)
    txt(trend_x+14, mid_y+panel_h-18, "TREND", 6.8, HexColor(BLUE))
    txt(trend_x+14, mid_y+panel_h-35, "県全体の推移（直近3か月）", 11.5, NAVY)
    draw_img_fit(c, trend_png, trend_x+10, mid_y+10, trend_w-20, panel_h-52)

    # Bottom ranking + YOY
    by, bh = 39, 154
    rank_x, rank_w = 22, 490
    card(rank_x, by, rank_w, bh)
    txt(rank_x+14, by+bh-18, "REGIONAL RANKING", 6.8, HexColor(BLUE))
    txt(rank_x+14, by+bh-35, "地域別ランキング", 11.5, NAVY)
    regions = sorted((latest.get("regions") or {}).items(), key=lambda kv: float(kv[1]), reverse=True)
    for idx,(name,value) in enumerate(regions):
        col = 0 if idx < 7 else 1
        row = idx if idx < 7 else idx-7
        xx = rank_x+14+col*232
        yy = by+bh-54-row*13.3
        display = "新潟" if name == "新潟市" else name
        c.setFillColor(HexColor(tier_color(float(value))))
        c.circle(xx+3.5, yy+1.5, 3, fill=1, stroke=0)
        txt(xx+12, yy-1, f"{idx+1:>2}  {display}", 7.4)
        right(xx+210, yy-1, f"{float(value):.2f}".rstrip("0").rstrip("."), 7.8, NAVY)

    yoy_x = 524
    yoy_w = W-yoy_x-22
    card(yoy_x, by, yoy_w, bh)
    txt(yoy_x+14, by+bh-18, "YEAR ON YEAR", 6.8, HexColor(BLUE))
    txt(yoy_x+14, by+bh-35, "前年同期との比較", 11.5, NAVY)

    last_year = next(
        (w for w in weeks if int(w["year"]) == int(latest["year"])-1 and int(w["week"]) == int(latest["week"])),
        None,
    )
    if last_year:
        txt(yoy_x+18, by+90, f"{last_year['year']} 第{last_year['week']}週", 7.2, MUTED)
        txt(yoy_x+18, by+68, f"{float(last_year.get('prefecture') or 0):.2f}", 18, HexColor(BLUE))
        txt(yoy_x+90, by+70, "→", 15, MUTED)
        txt(yoy_x+118, by+90, f"{latest['year']} 第{latest['week']}週", 7.2, MUTED)
        txt(yoy_x+118, by+68, f"{float(latest.get('prefecture') or 0):.2f}", 18, HexColor(tier_color(val)))
    yoy_lines = wrap_ja(c, ai.get("year_on_year",""), yoy_w-28, size=7.3)
    for j,line in enumerate(yoy_lines[:3]):
        txt(yoy_x+14, by+38-j*10.5, line, 7.3)

    # Footer
    c.setStrokeColor(LINE)
    c.line(22, 28, W-22, 28)
    disclaimer = ai.get("disclaimer","新潟県公表データをもとにAIが自動生成した分析コメントです。")
    foot = disclaimer + " 本資料は非公式レポートです。"
    for j,line in enumerate(wrap_ja(c, foot, W-140, size=5.8)[:2]):
        txt(22, 17-j*7, line, 5.8, MUTED)
    right(W-82, 16, "Powered by CivITech", 6.2, MUTED)
    if QR_PATH.exists():
        c.drawImage(str(QR_PATH), W-66, 4, 30, 30, mask="auto")

    c.showPage()
    c.save()

    # Stable latest.pdf for the web download button.
    latest_name.write_bytes(dated_name.read_bytes())
    print(dated_name)
    print(latest_name)

def main():
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"{DATA_PATH} がありません。")
    if not AI_PATH.exists():
        raise FileNotFoundError(f"{AI_PATH} がありません。先にAIコメントを生成してください。")
    build_report(load_json(DATA_PATH), load_json(AI_PATH))

if __name__ == "__main__":
    main()
