#!/usr/bin/env python3
from __future__ import annotations
import html, json, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
DATA_PATH=ROOT/'data'/'influenza_history.json'
AI_PATH=ROOT/'data'/'ai_comment.json'
REPORT_DIR=ROOT/'reports'
ASSET_DIR=ROOT/'.report_assets'
GEO_CACHE=ASSET_DIR/'niigata_municipalities.geojson'
GEO_URL='https://raw.githubusercontent.com/smartnews-smri/japan-topography/refs/heads/main/data/municipality/geojson/s0010/N03-21_15_210101.json'
BLUE='#0b79b6';YELLOW='#f2c94c';RED='#ef6a5b';PURPLE='#7b4bb7'
REGION_MUNICIPALITIES={
'村上':['村上市','関川村','粟島浦村'],'新発田':['新発田市','阿賀野市','胎内市','聖籠町'],'新潟市':['新潟市'],'新津':['五泉市','阿賀町'],'三条':['三条市','加茂市','燕市','弥彦村','田上町'],'長岡':['長岡市','小千谷市','見附市','出雲崎町'],'魚沼':['魚沼市'],'南魚沼':['南魚沼市','湯沢町'],'十日町':['十日町市','津南町'],'柏崎':['柏崎市','刈羽村'],'上越':['上越市','妙高市'],'糸魚川':['糸魚川市'],'佐渡':['佐渡市']}
MUNI_TO_REGION={m:r for r,ms in REGION_MUNICIPALITIES.items() for m in ms}

def load_json(p): return json.loads(p.read_text(encoding='utf-8'))
def weeks_sorted(h): return sorted(h.get('weeks',[]),key=lambda w:(int(w['year']),int(w['week'])))
def tier(v):
    v=float(v or 0)
    return PURPLE if v>=30 else RED if v>=10 else YELLOW if v>=1 else BLUE

def region_for_feature(p):
    if p.get('N03_003')=='新潟市': return '新潟市'
    for k in ('N03_004','N03_003','N03_002'):
        n=p.get(k)
        if n in MUNI_TO_REGION: return MUNI_TO_REGION[n]
    return None

def rings(g):
    if not g:return []
    if g.get('type')=='Polygon': return [g['coordinates'][0]]
    if g.get('type')=='MultiPolygon': return [poly[0] for poly in g['coordinates']]
    return []

def get_geo():
    ASSET_DIR.mkdir(exist_ok=True)
    if not GEO_CACHE.exists():
        with urllib.request.urlopen(GEO_URL,timeout=30) as r:GEO_CACHE.write_bytes(r.read())
    return load_json(GEO_CACHE)

def map_svg(latest,w=560,h=235):
    feats=[];xs=[];ys=[]
    for f in get_geo().get('features',[]):
        reg=region_for_feature(f.get('properties') or {})
        col=tier((latest.get('regions') or {}).get(reg,0))
        for ring in rings(f.get('geometry')):
            pts=[(float(x),float(y)) for x,y in ring]
            if len(pts)<3:continue
            feats.append((pts,col));xs += [x for x,_ in pts];ys += [y for _,y in pts]
    if not xs:return ''
    minx,maxx,miny,maxy=min(xs),max(xs),min(ys),max(ys);pad=7
    s=min((w-2*pad)/(maxx-minx),(h-2*pad)/(maxy-miny));ox=(w-(maxx-minx)*s)/2;oy=(h-(maxy-miny)*s)/2
    polys=[]
    for pts,col in feats:
        coords=' '.join(f'{ox+(x-minx)*s:.1f},{h-(oy+(y-miny)*s):.1f}' for x,y in pts)
        polys.append(f'<polygon points="{coords}" fill="{col}" stroke="white" stroke-width="0.45"/>')
    return f'<svg viewBox="0 0 {w} {h}" class="map-svg"><rect width="{w}" height="{h}" fill="#edf6fb"/>{"".join(polys)}</svg>'

def trend_svg(weeks,w=420,h=190):
    cur=weeks[-13:]
    if not cur:return ''
    vals=[float(x.get('prefecture') or 0) for x in cur]
    prev=[]
    for wk in cur:
        p=next((x for x in weeks if int(x['year'])==int(wk['year'])-1 and int(x['week'])==int(wk['week'])),None)
        prev.append(None if p is None else float(p.get('prefecture') or 0))
    vmax=max([30]+vals+[x for x in prev if x is not None]);left,right,top,bottom=34,10,14,32;pw=w-left-right;ph=h-top-bottom
    X=lambda i:left+(0 if len(cur)==1 else i/(len(cur)-1)*pw);Y=lambda v:top+ph-(v/vmax*ph)
    grid=''.join(f'<line x1="{left}" x2="{w-right}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#dbe8ef"/><text x="{left-6}" y="{Y(v)+3:.1f}" text-anchor="end" font-size="8" fill="#718795">{v}</text>' for v in (0,1,10,30) if v<=vmax)
    curpts=' '.join(f'{X(i):.1f},{Y(v):.1f}' for i,v in enumerate(vals))
    prevpts=' '.join(f'{X(i):.1f},{Y(v):.1f}' for i,v in enumerate(prev) if v is not None)
    labels=''.join(f'<text x="{X(i):.1f}" y="{h-9}" text-anchor="middle" font-size="7.2" fill="#718795">{html.escape(wk.get("label",""))}</text>' for i,wk in enumerate(cur) if i%2==0 or i==len(cur)-1)
    dots=''.join(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="2.4" fill="{BLUE}"/>' for i,v in enumerate(vals))
    return f'<svg viewBox="0 0 {w} {h}" class="trend-svg"><rect width="{w}" height="{h}" fill="#f8fcfe"/>{grid}<polyline points="{prevpts}" fill="none" stroke="#8fa3b1" stroke-width="2" stroke-dasharray="6 5"/><polyline points="{curpts}" fill="none" stroke="{BLUE}" stroke-width="2.6"/>{dots}{labels}</svg>'

def fmt(v):
    if v is None:return '-'
    return f'{float(v):.2f}'.rstrip('0').rstrip('.')

def build_html(history,ai):
    weeks=weeks_sorted(history);latest=weeks[-1];prev=weeks[-2] if len(weeks)>1 else None;prev2=weeks[-3] if len(weeks)>2 else None
    src=ai.get('source_week') or {}
    if int(src.get('year',-1))!=int(latest['year']) or int(src.get('week',-1))!=int(latest['week']):raise RuntimeError('ai_comment.json が最新週と一致しません。')
    regs=sorted((latest.get('regions') or {}).items(),key=lambda kv:float(kv[1]),reverse=True)
    ranks=''.join(f'<div class="rank-item"><span class="dot" style="background:{tier(v)}"></span><span>{i+1}</span><span>{html.escape("新潟" if n=="新潟市" else n)}</span><b>{fmt(v)}</b></div>' for i,(n,v) in enumerate(regs))
    ly=next((x for x in weeks if int(x['year'])==int(latest['year'])-1 and int(x['week'])==int(latest['week'])),None)
    insight=' '.join(x for x in (ai.get('summary',''),ai.get('trend',''),ai.get('regional',''),ai.get('year_on_year','')) if x)
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><style>
@page{{size:A4 landscape;margin:0}}*{{box-sizing:border-box}}html,body{{margin:0;background:#edf4f8;color:#18394f;font-family:"Noto Sans CJK JP","Noto Sans JP","Yu Gothic","Meiryo",sans-serif}}.page{{width:297mm;height:210mm;padding:9mm 10mm 7mm;overflow:hidden}}.header{{height:19mm;margin:-9mm -10mm 5mm;padding:7mm 10mm 0;background:#fff;display:flex;justify-content:space-between}}h1{{margin:0;color:#103f67;font-size:18px}}small{{color:#688090;font-size:8px}}.meta{{text-align:right;color:#103f67;font-size:11px;font-weight:800}}.top{{display:grid;grid-template-columns:54mm 1fr;gap:4mm;margin-bottom:4mm}}.card{{background:#fff;border:1px solid #d8e7f0;border-radius:11px;padding:4mm}}.k{{font-size:7px;font-weight:900;letter-spacing:.08em;color:#0b79b6;margin-bottom:2mm}}.metric .big{{font-size:30px;font-weight:900;color:{tier(latest.get('prefecture'))}}}.unit{{font-size:8px;color:#688090;margin-left:2mm}}.mini{{display:flex;gap:7mm;margin-top:4mm;font-size:8px;color:#688090}}.mini b{{color:#103f67;font-size:10px}}.insight h2{{font-size:13px;color:#103f67;margin:0 0 2mm}}.insight p{{font-size:8.2px;line-height:1.62;margin:0}}.middle{{display:grid;grid-template-columns:1.15fr .85fr;gap:4mm;margin-bottom:4mm;height:76mm}}.pt{{font-size:12px;font-weight:900;color:#103f67;margin-bottom:2mm}}.map-svg{{width:100%;height:62mm}}.trend-svg{{width:100%;height:58mm}}.trend-legend{{display:flex;gap:5mm;align-items:center;margin:-1mm 0 1mm;font-size:7.5px;color:#607887}}.trend-legend span{{display:inline-flex;align-items:center;gap:1.5mm}}.trend-line{{display:inline-block;width:8mm;height:0;border-top:2px solid #0b79b6}}.trend-line.prev{{border-top-color:#8fa3b1;border-top-style:dashed}}.bottom{{display:grid;grid-template-columns:1.25fr .75fr;gap:4mm;height:53mm}}.ranks{{display:grid;grid-template-columns:1fr 1fr;gap:1mm 5mm}}.rank-item{{display:grid;grid-template-columns:7px 17px 1fr auto;align-items:center;font-size:8px;padding:1.1mm 0;border-bottom:1px solid #edf2f5}}.dot{{width:6px;height:6px;border-radius:50%}}.yoyrow{{display:flex;align-items:end;gap:6mm;margin:5mm 0 4mm}}.yoybox strong{{font-size:22px;color:#103f67}}.arrow{{font-size:20px;color:#8fa3b1}}.yoy p{{font-size:8.2px;line-height:1.5}}.footer{{height:12mm;margin-top:3mm;border-top:1px solid #d8e7f0;padding-top:2mm;display:flex;justify-content:space-between;color:#688090;font-size:6.5px;line-height:1.45}}
</style></head><body><div class="page"><div class="header"><div><h1>インフルエンザレポート（新潟県）</h1><small>NIIGATA INFLUENZA WEEKLY REPORT</small></div><div class="meta">{latest['year']} 第{latest['week']}週（{html.escape(latest.get('label',''))}）<br><small>データ出典：新潟県 感染症情報（週報）</small></div></div><div class="top"><section class="card metric"><small>県全体・定点当たり報告数</small><div><span class="big">{fmt(latest.get('prefecture'))}</span><span class="unit">人／定点</span></div><div class="mini"><span>前週 <b>{fmt(prev.get('prefecture') if prev else None)}</b></span><span>前々週 <b>{fmt(prev2.get('prefecture') if prev2 else None)}</b></span></div></section><section class="card insight"><div class="k">AI WEEKLY INSIGHT</div><h2>{html.escape(ai.get('headline','今週の流行分析'))}</h2><p>{html.escape(insight)}</p></section></div><div class="middle"><section class="card"><div class="k">AREA MAP</div><div class="pt">地域別の流行状況</div>{map_svg(latest)}</section><section class="card"><div class="k">TREND</div><div class="pt">県全体の推移（直近3か月）</div><div class="trend-legend"><span><i class="trend-line"></i>今年（{latest['year']}）</span><span><i class="trend-line prev"></i>前年同期（{int(latest['year'])-1}）</span></div>{trend_svg(weeks)}</section></div><div class="bottom"><section class="card"><div class="k">REGIONAL RANKING</div><div class="pt">地域別ランキング</div><div class="ranks">{ranks}</div></section><section class="card yoy"><div class="k">YEAR ON YEAR</div><div class="pt">前年同期との比較</div><div class="yoyrow"><div class="yoybox"><small>{int(latest['year'])-1} 第{latest['week']}週</small><br><strong>{fmt(ly.get('prefecture') if ly else None)}</strong></div><div class="arrow">→</div><div class="yoybox"><small>{latest['year']} 第{latest['week']}週</small><br><strong style="color:{tier(latest.get('prefecture'))}">{fmt(latest.get('prefecture'))}</strong></div></div><p>{html.escape(ai.get('year_on_year',''))}</p></section></div><div class="footer"><div>{html.escape(ai.get('disclaimer',''))} 本資料は非公式レポートです。</div><div>Powered by CivITech</div></div></div></body></html>'''

def main():
    history=load_json(DATA_PATH);ai=load_json(AI_PATH);weeks=weeks_sorted(history);latest=weeks[-1]
    REPORT_DIR.mkdir(exist_ok=True);ASSET_DIR.mkdir(exist_ok=True)
    hp=ASSET_DIR/'weekly_report.html';hp.write_text(build_html(history,ai),encoding='utf-8')
    dated=REPORT_DIR/f"niigata_influenza_report_{latest['year']}W{int(latest['week']):02d}.pdf";latest_pdf=REPORT_DIR/'latest.pdf'
    with sync_playwright() as p:
        
        launch_kwargs={'headless':True}
        system_chromium=Path('/usr/bin/chromium')
        if system_chromium.exists(): launch_kwargs['executable_path']=str(system_chromium)
        browser=p.chromium.launch(**launch_kwargs);page=browser.new_page(viewport={'width':1600,'height':1131});page.set_content(hp.read_text(encoding='utf-8'),wait_until='load');page.emulate_media(media='print');page.pdf(path=str(dated),format='A4',landscape=True,print_background=True,margin={'top':'0','right':'0','bottom':'0','left':'0'},prefer_css_page_size=True);browser.close()
    latest_pdf.write_bytes(dated.read_bytes());print('OK',dated);print('OK',latest_pdf)
if __name__=='__main__':main()
