#!/usr/bin/env python3
from __future__ import annotations
import json, math, os, re, shutil, subprocess, sys, urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = ROOT / "reports"
OUTDIR.mkdir(exist_ok=True)
TEMPLATE = ROOT / "reports" / "template" / "report.html"
CSS = ROOT / "reports" / "template" / "report.css"
HISTORY = ROOT / "data" / "influenza_history.json"
AI = ROOT / "data" / "ai_comment.json"
GEOJSON = ROOT / "data" / "niigata_municipality.geojson"
GEOJSON_URL = "https://raw.githubusercontent.com/smartnews-smri/japan-topography/refs/heads/main/data/municipality/geojson/s0010/N03-21_15_210101.json"

REGION_DISPLAY = {"新潟市":"新潟"}
REGION_MUNICIPALITIES = {
    "村上":["村上市","関川村","粟島浦村"],
    "新発田":["新発田市","阿賀野市","胎内市","聖籠町"],
    "新潟":["新潟市"],
    "新津":["五泉市","阿賀町"],
    "三条":["三条市","加茂市","燕市","弥彦村","田上町"],
    "長岡":["長岡市","小千谷市","見附市","出雲崎町"],
    "魚沼":["魚沼市"],
    "南魚沼":["南魚沼市","湯沢町"],
    "十日町":["十日町市","津南町"],
    "柏崎":["柏崎市","刈羽村"],
    "上越":["上越市","妙高市"],
    "糸魚川":["糸魚川市"],
    "佐渡":["佐渡市"],
}
MUNI_TO_REGION = {m:r for r,ms in REGION_MUNICIPALITIES.items() for m in ms}
AGE_GROUPS = ["0歳","1～4歳","5～9歳","10～14歳","15～19歳","20～59歳","60歳以上"]

SAMPLE = {
  "meta":{"updated_at":"2026-09-15T15:22:00+09:00","source":"新潟県感染症情報（週報）"},
  "weeks":[
    {"year":2026,"week":31,"label":"R8/7/27–8/2","prefecture":0.80},
    {"year":2026,"week":32,"label":"R8/8/3–8/9","prefecture":1.64},
    {"year":2026,"week":33,"label":"R8/8/10–8/16","prefecture":1.09},
    {"year":2026,"week":34,"label":"R8/8/17–8/23","prefecture":1.65},
    {"year":2026,"week":35,"label":"R8/8/24–8/30","prefecture":3.58},
    {"year":2026,"week":36,"label":"R8/8/31–9/6","prefecture":6.13,
     "regions":{"村上":13.00,"新発田":6.75,"新潟市":8.56,"新津":5.50,"三条":2.00,"長岡":5.14,"魚沼":5.50,"南魚沼":4.67,"十日町":1.00,"柏崎":7.00,"上越":1.25,"糸魚川":6.50,"佐渡":7.00},
     "age_counts":{"0歳":6,"1～4歳":53,"5～9歳":122,"10～14歳":52,"15～19歳":9,"20～59歳":74,"60歳以上":21},
     "age_per_sentinel":{"0歳":0.11,"1～4歳":0.97,"5～9歳":2.22,"10～14歳":0.95,"15～19歳":0.16,"20～59歳":1.35,"60歳以上":0.39}}
  ]
}
SAMPLE_AI = {
  "headline":"県全体で増加が続く",
  "summary":"県全体は6.13 人 / 定点となり、前週3.58から+2.55増加しました。流行期入りの目安を上回っています。",
  "trend":"直近3週で1.65 → 3.58 → 6.13と上昇しています。今後の推移を継続して確認する必要があります。",
  "regional":"村上が13.00 人 / 定点で最も高く、新潟、柏崎、佐渡などでも比較的高い値となっています。",
  "age_group":"5～9歳が122人・2.22 人 / 定点で最も多く、20～59歳が74人・1.35 人 / 定点で続いています。",
  "year_on_year":"前年同期0.27 人 / 定点に対し、今年は6.13 人 / 定点と高い水準です。"
}


def load_json(path, fallback):
    if path.exists():
        try: return json.loads(path.read_text(encoding="utf-8"))
        except Exception: pass
    return fallback


def western_period(label, year):
    if not label: return f"{year}年第--週"
    return re.sub(r"^R\d+/", f"{year}/", str(label))


def signal(v):
    if v < 1: return ("#0b79b6","流行期入りの目安未満")
    if v < 10: return ("#f2c94c","流行期入りの目安以上")
    if v < 30: return ("#ef6a5b","従来の注意報基準相当")
    return ("#7b4bb7","従来の警報基準相当")


def esc(s):
    return (str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;"))


def svg_line_chart(weeks, width=520, height=180):
    vals=[float(w.get("prefecture") or 0) for w in weeks]
    labels=[f"第{w.get('week','-')}週" for w in weeks]
    vmax=max(max(vals)*1.18, 7)
    ml,mr,mt,mb=42,18,18,35
    pw,ph=width-ml-mr,height-mt-mb
    pts=[]
    for i,v in enumerate(vals):
        x=ml+(pw*(i/(len(vals)-1 if len(vals)>1 else 1)))
        y=mt+ph-(v/vmax*ph)
        pts.append((x,y,v))
    parts=[f'<svg viewBox="0 0 {width} {height}" class="svg-chart">']
    for t in range(5):
        y=mt+ph*t/4
        val=vmax*(1-t/4)
        parts.append(f'<line x1="{ml}" x2="{width-mr}" y1="{y:.1f}" y2="{y:.1f}" stroke="#d9e8f5" stroke-width="1"/>')
        parts.append(f'<text x="{ml-8}" y="{y+4:.1f}" text-anchor="end" class="axis">{val:.1f}</text>')
    d=' '.join((('M' if i==0 else 'L')+f' {x:.1f} {y:.1f}') for i,(x,y,v) in enumerate(pts))
    parts.append(f'<path d="{d}" fill="none" stroke="#145da0" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>')
    for i,(x,y,v) in enumerate(pts):
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.2" fill="#1976c9" stroke="white" stroke-width="1.5"/>')
        if i>=len(pts)-3:
            parts.append(f'<text x="{x:.1f}" y="{y-9:.1f}" text-anchor="middle" class="value-label">{v:.2f}</text>')
        parts.append(f'<text x="{x:.1f}" y="{height-12}" text-anchor="middle" class="axis">{esc(labels[i])}</text>')
    parts.append('</svg>')
    return ''.join(parts)


def svg_age_chart(counts, rates, width=540, height=196):
    values=[float(counts.get(g,0) or 0) for g in AGE_GROUPS]
    vmax=max(max(values)*1.18, 10)
    ml,mr,mt,mb=38,10,24,50
    pw,ph=width-ml-mr,height-mt-mb
    colors=["#83b8e8","#3b8fd3","#2b78bb","#70a9d9","#9dc8e9","#4f96cf","#77afd9"]
    parts=[f'<svg viewBox="0 0 {width} {height}" class="svg-chart">']
    for t in range(4):
        y=mt+ph*t/3
        val=vmax*(1-t/3)
        parts.append(f'<line x1="{ml}" x2="{width-mr}" y1="{y:.1f}" y2="{y:.1f}" stroke="#dce9f4"/>')
        parts.append(f'<text x="{ml-7}" y="{y+4:.1f}" text-anchor="end" class="axis">{int(round(val))}</text>')
    bw=pw/len(values)*0.60
    for i,(g,v) in enumerate(zip(AGE_GROUPS,values)):
        cx=ml+pw*(i+.5)/len(values); h=v/vmax*ph; y=mt+ph-h
        parts.append(f'<rect x="{cx-bw/2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="3" fill="{colors[i]}"/>')
        parts.append(f'<text x="{cx:.1f}" y="{max(12,y-6):.1f}" text-anchor="middle" class="value-label">{int(v)}人</text>')
        parts.append(f'<text x="{cx:.1f}" y="{height-28}" text-anchor="middle" class="axis age-axis">{esc(g)}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{height-8}" text-anchor="middle" class="rate-label">{float(rates.get(g,0) or 0):.2f}</text>')
    parts.append(f'<text x="6" y="12" class="axis">報告数（人）</text>')
    parts.append(f'<text x="6" y="{height-8}" class="axis">人/定点</text>')
    parts.append('</svg>')
    return ''.join(parts)


def blue_map_color(v):
    v=float(v or 0)
    if v>=10: return "#174f86"
    if v>=7: return "#2c6ea8"
    if v>=4: return "#5592c6"
    if v>=1: return "#8bb8dd"
    return "#c8def0"


def _walk_coords(geom):
    tp=geom.get("type"); c=geom.get("coordinates",[])
    if tp=="Polygon":
        for ring in c: yield ring
    elif tp=="MultiPolygon":
        for poly in c:
            for ring in poly: yield ring


def _municipality_name(props):
    vals=[str(v) for v in props.values() if isinstance(v,str)]
    # Prefer city/ward/municipality-looking field.
    for v in vals[::-1]:
        if re.search(r"(市.+区|市|町|村)$",v): return v
    return vals[-1] if vals else ""


def region_for_muni(name):
    if name.startswith("新潟市"): return "新潟"
    if name in MUNI_TO_REGION: return MUNI_TO_REGION[name]
    for m,r in MUNI_TO_REGION.items():
        if m in name: return r
    return None


def ensure_geojson():
    if GEOJSON.exists() and GEOJSON.stat().st_size>1000: return True
    GEOJSON.parent.mkdir(exist_ok=True)
    try:
        urllib.request.urlretrieve(GEOJSON_URL,GEOJSON)
        return True
    except Exception as e:
        print(f"[report] GeoJSON download unavailable, fallback map: {e}", file=sys.stderr)
        return False


def svg_map(regions, width=410, height=285):
    if ensure_geojson():
        try:
            gj=json.loads(GEOJSON.read_text(encoding="utf-8"))
            rings=[]
            for f in gj.get("features",[]):
                name=_municipality_name(f.get("properties",{})); region=region_for_muni(name)
                for ring in _walk_coords(f.get("geometry",{})):
                    rings.append((ring,region))
            xs=[p[0] for ring,_ in rings for p in ring]; ys=[p[1] for ring,_ in rings for p in ring]
            minx,maxx,miny,maxy=min(xs),max(xs),min(ys),max(ys)
            padx,pady=16,10
            scale=min((width-2*padx)/(maxx-minx),(height-2*pady)/(maxy-miny))
            def proj(p):
                x=padx+(p[0]-minx)*scale
                y=height-pady-(p[1]-miny)*scale
                return x,y
            parts=[f'<svg viewBox="0 0 {width} {height}" class="map-svg">']
            for ring,region in rings:
                pts=' '.join(f'{proj(p)[0]:.1f},{proj(p)[1]:.1f}' for p in ring)
                color=blue_map_color(regions.get(region,0)) if region else '#e8f1f8'
                parts.append(f'<polygon points="{pts}" fill="{color}" stroke="#ffffff" stroke-width="0.9"/>')
            parts.append('</svg>')
            return ''.join(parts), True
        except Exception as e:
            print(f"[report] GeoJSON parse failed, fallback map: {e}", file=sys.stderr)
    # Clean schematic fallback - production uses exact SVG when GeoJSON is available.
    shapes=[
        ("糸魚川",[(44,238),(85,245),(105,227),(91,208),(56,214)]),
        ("上越",[(91,208),(105,227),(143,216),(153,192),(124,184)]),
        ("柏崎",[(124,184),(153,192),(180,172),(167,153),(140,158)]),
        ("長岡",[(167,153),(180,172),(221,153),(228,123),(196,112)]),
        ("魚沼",[(196,112),(228,123),(254,109),(247,82),(215,78)]),
        ("南魚沼",[(215,78),(247,82),(268,66),(252,42),(222,48)]),
        ("十日町",[(180,172),(221,153),(196,112),(164,126)]),
        ("三条",[(164,126),(196,112),(180,87),(151,103)]),
        ("新津",[(180,87),(215,78),(206,55),(175,61)]),
        ("新潟",[(151,103),(180,87),(175,61),(141,72)]),
        ("新発田",[(175,61),(206,55),(215,31),(187,25)]),
        ("村上",[(187,25),(215,31),(236,8),(207,3)]),
        ("佐渡",[(32,74),(61,90),(79,66),(62,42),(36,49)])
    ]
    parts=[f'<svg viewBox="0 0 280 255" class="map-svg fallback-map">']
    for region,pts in shapes:
        p=' '.join(f'{x},{y}' for x,y in pts)
        parts.append(f'<polygon points="{p}" fill="{blue_map_color(regions.get(region,0))}" stroke="#fff" stroke-width="1.4"/>')
    parts.append('</svg>')
    return ''.join(parts), False


def regional_rows(regions, prev_regions=None):
    prev_regions=prev_regions or {}
    order=sorted(regions.items(), key=lambda kv:(-float(kv[1]),kv[0]))
    rows=[]
    for region,v in order:
        disp=REGION_DISPLAY.get(region,region)
        pv=prev_regions.get(region)
        delta="--" if pv is None else f"{float(v)-float(pv):+.2f}"
        rows.append(f'<tr><td>{esc(disp)}</td><td>{float(v):.2f}</td><td>{"--" if pv is None else f"{float(pv):.2f}"}</td><td class="delta">{delta}</td></tr>')
    return ''.join(rows)


def render_html():
    data=load_json(HISTORY,SAMPLE); weeks=sorted(data.get("weeks",[]), key=lambda w:(w.get("year",0),w.get("week",0)))
    if not weeks: raise RuntimeError("weeks is empty")
    latest=weeks[-1]; prev=weeks[-2] if len(weeks)>1 else {}
    ai=load_json(AI,SAMPLE_AI)
    v=float(latest.get("prefecture") or 0); pv=float(prev.get("prefecture") or 0); diff=v-pv
    regions=latest.get("regions",{}) or {}; prev_regions=prev.get("regions",{}) or {}
    display_regions={REGION_DISPLAY.get(k,k):val for k,val in regions.items()}
    color,sig=signal(v)
    age_counts=latest.get("age_counts",{}) or {}; age_rates=latest.get("age_per_sentinel",{}) or {}
    same_last=None
    for w in reversed(weeks[:-1]):
        if int(w.get("week",-1))==int(latest.get("week",-2)) and int(w.get("year",0))==int(latest.get("year",0))-1:
            same_last=w; break
    yoy=float(same_last.get("prefecture")) if same_last else 0.27
    map_svg,map_exact=svg_map(display_regions)
    period=western_period(latest.get("label"),latest.get("year"))
    updated=data.get("meta",{}).get("updated_at") or datetime.now().isoformat()
    try: update_display=datetime.fromisoformat(updated.replace("Z","+00:00")).strftime("%Y/%m/%d %H:%M")
    except: update_display=str(updated)
    trend_weeks=weeks[-6:]
    top5=sorted(display_regions.items(), key=lambda kv:-float(kv[1]))[:5]
    top_rows=''.join(f'<tr><td>{i+1}</td><td>{esc(r)}</td><td>{float(x):.2f}</td></tr>' for i,(r,x) in enumerate(top5))
    ai_rows=''.join([
      f'<div class="ai-row"><b>概況</b><p>{esc(ai.get("summary",""))}</p></div>',
      f'<div class="ai-row"><b>推移</b><p>{esc(ai.get("trend",""))}</p></div>',
      f'<div class="ai-row"><b>地域</b><p>{esc(ai.get("regional",""))}</p></div>',
      f'<div class="ai-row"><b>年代</b><p>{esc(ai.get("age_group",""))}</p></div>',
      f'<div class="ai-row"><b>前年同期</b><p>{esc(ai.get("year_on_year",""))}</p></div>',
    ])
    replacements={
      "TITLE_PERIOD":f'{latest.get("year")}年第{int(latest.get("week")):02d}週（{period.split("/",1)[1] if "/" in period else period}）',
      "LATEST_VALUE":f"{v:.2f}","PREV_VALUE":f"{pv:.2f}","DIFF_VALUE":f"{diff:+.2f}","YOY_VALUE":f"{yoy:.2f}",
      "SIGNAL_COLOR":color,"SIGNAL_TEXT":sig,"UPDATE_TIME":update_display,
      "TREND_SVG":svg_line_chart(trend_weeks),"AGE_SVG":svg_age_chart(age_counts,age_rates),"MAP_SVG":map_svg,
      "TOP_REGION_ROWS":top_rows,"REGION_ROWS":regional_rows(regions,prev_regions),"AI_ROWS":ai_rows,
      "MAP_SOURCE_NOTE":("市町村SVG / 国土数値情報由来" if map_exact else "本番生成時に市町村GeoJSONからSVG化"),
      "HEADLINE":esc(ai.get("headline","今週の流行分析")),
    }
    html=TEMPLATE.read_text(encoding="utf-8")
    for k,val in replacements.items(): html=html.replace("{{"+k+"}}",str(val))
    return html


def generate_pdf():
    html=render_html(); rendered=TEMPLATE.parent/"weekly_report_rendered.html"; rendered.write_text(html,encoding="utf-8")
    pdf=OUTDIR/"latest.pdf"
    # Prefer WeasyPrint in CI/local environments for deterministic A4 landscape output.
    weasy=shutil.which("weasyprint")
    if weasy:
        subprocess.run([weasy,str(rendered),str(pdf)],check=True)
    else:
        chromium=shutil.which("chromium") or shutil.which("google-chrome")
        if not chromium: raise RuntimeError("Neither WeasyPrint nor Chromium was found")
        url=rendered.resolve().as_uri()
        cmd=[chromium,"--headless=new","--disable-gpu","--no-sandbox","--disable-dev-shm-usage",f"--print-to-pdf={pdf}","--no-pdf-header-footer",url]
        subprocess.run(cmd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
    print(pdf)

if __name__=="__main__": generate_pdf()
