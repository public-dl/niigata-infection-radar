#!/usr/bin/env python3
from __future__ import annotations
import json
import os, math, os, re, shutil, subprocess, sys, urllib.request
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HISTORY=Path(os.environ.get('INFLUENZA_HISTORY_PATH', ROOT/'data'/'influenza_history.json'))
AI=Path(os.environ.get('AI_COMMENT_PATH', ROOT/'data'/'ai_comment.json'))
TEMPLATE=ROOT/'reports'/'template'/'report.html'
OUT=ROOT/'reports'
OUT.mkdir(exist_ok=True)
AGE_GROUPS=['0歳','1～4歳','5～9歳','10～14歳','15～19歳','20～59歳','60歳以上']
REGION_DISPLAY={'新潟市':'新潟'}
REGION_ORDER=['新潟市','新発田','村上','長岡','柏崎','上越','糸魚川','南魚沼','十日町','佐渡','新津','三条','魚沼']
GEOJSON=ROOT/'data'/'niigata_municipality.geojson'
GEOJSON_URL='https://raw.githubusercontent.com/smartnews-smri/japan-topography/refs/heads/main/data/municipality/geojson/s0010/N03-21_15_210101.json'
REGION_MUNICIPALITIES={
 '村上':['村上市','関川村','粟島浦村'],
 '新発田':['新発田市','阿賀野市','胎内市','聖籠町'],
 '新潟':['新潟市'],
 '新津':['五泉市','阿賀町'],
 '三条':['三条市','加茂市','燕市','弥彦村','田上町'],
 '長岡':['長岡市','小千谷市','見附市','出雲崎町'],
 '魚沼':['魚沼市'],
 '南魚沼':['南魚沼市','湯沢町'],
 '十日町':['十日町市','津南町'],
 '柏崎':['柏崎市','刈羽村'],
 '上越':['上越市','妙高市'],
 '糸魚川':['糸魚川市'],
 '佐渡':['佐渡市'],
}
MUNI_TO_REGION={m:r for r,ms in REGION_MUNICIPALITIES.items() for m in ms}
COLORS=['#4e9bd7','#7cb9e5','#3a83bf','#5f9fd0','#8bbbe0','#4e91c8','#6ca8d6']

def load(path, fallback):
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    return fallback

def esc(x):
    return str(x).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def signal(v):
    if v < 1: return '#0b79b6','流行期入りの目安未満','blue'
    if v < 10: return '#f2c94c','流行期入りの目安以上','yellow'
    if v < 30: return '#ef6a5b','従来の注意報基準相当','red'
    return '#7b4bb7','従来の警報基準相当','purple'

def period_text(w):
    label=str(w.get('label',''))
    m=re.search(r'R\d+/(.+)',label)
    tail=m.group(1) if m else label
    return f"{w.get('year')}年第{int(w.get('week')):02d}週（{tail}）"

def svg_trend(weeks,w=430,h=170):
    vals=[float(x.get('prefecture') or 0) for x in weeks]
    vmax=max(7.0,max(vals)*1.12)
    ml,mr,mt,mb=50,8,12,30
    pw,ph=w-ml-mr,h-mt-mb
    pts=[]
    for i,v in enumerate(vals):
        x=ml+pw*(i/(max(1,len(vals)-1))); y=mt+ph-(v/vmax)*ph; pts.append((x,y,v))
    s=[f'<svg viewBox="0 0 {w} {h}" class="svg-chart">']
    for t in range(5):
        y=mt+ph*t/4; val=vmax*(1-t/4)
        s.append(f'<line x1="{ml}" x2="{w-mr}" y1="{y:.1f}" y2="{y:.1f}" stroke="#dce8f2"/>')
        s.append(f'<text x="{ml-5}" y="{y+3:.1f}" text-anchor="end" class="axis">{val:.1f}</text>')
    d=' '.join((('M' if i==0 else 'L')+f' {x:.1f} {y:.1f}') for i,(x,y,v) in enumerate(pts))
    s.append(f'<path d="{d}" fill="none" stroke="#0f5fa8" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>')
    for i,(x,y,v) in enumerate(pts):
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.3" fill="#1976c9" stroke="white" stroke-width="1.6"/>')
        s.append(f'<text x="{x:.1f}" y="{max(12,y-8):.1f}" text-anchor="middle" class="value-label">{v:.2f}</text>')
        s.append(f'<text x="{x:.1f}" y="{h-9}" text-anchor="middle" class="axis">第{weeks[i].get("week")}週</text>')
    s.append('</svg>'); return ''.join(s)

def svg_age(counts,rates,w=520,h=195):
    vals=[float(counts.get(g,0) or 0) for g in AGE_GROUPS]
    vmax=max(150,max(vals)*1.15)
    ml,mr,mt,mb=30,8,15,31; pw,ph=w-ml-mr,h-mt-mb
    s=[f'<svg viewBox="0 0 {w} {h}" class="svg-chart">']
    for t in range(4):
        y=mt+ph*t/3; val=vmax*(1-t/3)
        s.append(f'<line x1="{ml}" x2="{w-mr}" y1="{y:.1f}" y2="{y:.1f}" stroke="#dce8f2"/>')
        s.append(f'<text x="{ml-5}" y="{y+3:.1f}" text-anchor="end" class="axis">{int(round(val))}</text>')
    bw=pw/len(vals)*.58
    for i,(g,v) in enumerate(zip(AGE_GROUPS,vals)):
        cx=ml+pw*(i+.5)/len(vals); bh=v/vmax*ph; y=mt+ph-bh
        s.append(f'<rect x="{cx-bw/2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="3" fill="{COLORS[i]}"/>')
        s.append(f'<text x="{cx:.1f}" y="{max(10,y-5):.1f}" text-anchor="middle" class="value-label">{int(v)}人</text>')
        s.append(f'<text x="{cx:.1f}" y="{h-9}" text-anchor="middle" class="axis age-axis">{esc(g)}</text>')
    s.append('</svg>'); return ''.join(s)

def _walk_coords(geom):
    tp=geom.get('type'); c=geom.get('coordinates',[])
    if tp=='Polygon':
        for ring in c: yield ring
    elif tp=='MultiPolygon':
        for poly in c:
            for ring in poly: yield ring

def _municipality_name(props):
    vals=[str(v) for v in props.values() if isinstance(v,str)]
    for v in vals[::-1]:
        if re.search(r'(市.+区|市|町|村)$',v): return v
    return vals[-1] if vals else ''

def _region_for_muni(name):
    if name.startswith('新潟市'): return '新潟'
    if name in MUNI_TO_REGION: return MUNI_TO_REGION[name]
    for m,r in MUNI_TO_REGION.items():
        if m in name: return r
    return None

def _map_color(v):
    v=float(v or 0)
    if v>=10: return '#174f86'
    if v>=7: return '#2c6ea8'
    if v>=4: return '#5592c6'
    if v>=1: return '#8bb8dd'
    return '#c8def0'

def _ensure_geojson():
    if GEOJSON.exists() and GEOJSON.stat().st_size>1000: return True
    GEOJSON.parent.mkdir(exist_ok=True)
    try:
        urllib.request.urlretrieve(GEOJSON_URL,GEOJSON)
        return True
    except Exception as e:
        print(f'[report] GeoJSON download unavailable, using preview fallback: {e}',file=sys.stderr)
        return False

def map_html(display_regions):
    if _ensure_geojson():
        try:
            gj=json.loads(GEOJSON.read_text(encoding='utf-8'))
            rings=[]
            for f in gj.get('features',[]):
                name=_municipality_name(f.get('properties',{})); region=_region_for_muni(name)
                for ring in _walk_coords(f.get('geometry',{})):
                    rings.append((ring,region))
            xs=[p[0] for ring,_ in rings for p in ring]; ys=[p[1] for ring,_ in rings for p in ring]
            minx,maxx,miny,maxy=min(xs),max(xs),min(ys),max(ys)
            width,height=350,310; padx,pady=12,8
            scale=min((width-2*padx)/(maxx-minx),(height-2*pady)/(maxy-miny))
            def proj(p):
                x=padx+(p[0]-minx)*scale; y=height-pady-(p[1]-miny)*scale
                return x,y
            parts=[f'<svg viewBox="0 0 {width} {height}" class="map-svg" aria-label="新潟県地域別マップ">']
            for ring,region in rings:
                pts=' '.join(f'{proj(p)[0]:.1f},{proj(p)[1]:.1f}' for p in ring)
                color=_map_color(display_regions.get(region,0)) if region else '#edf4f9'
                parts.append(f'<polygon points="{pts}" fill="{color}" stroke="#ffffff" stroke-width="1"/>')
            parts.append('</svg>')
            return ''.join(parts)
        except Exception as e:
            print(f'[report] GeoJSON parse failed, using preview fallback: {e}',file=sys.stderr)
    p=(TEMPLATE.parent/'assets'/'reference-map.png').resolve().as_uri()
    return f'<img src="{p}" alt="新潟県地域別マップ（オフラインプレビュー）">'

def fmt(v): return '--' if v is None else f'{float(v):.2f}'


def merge_week_records(raw_weeks):
    """
    同一年・同週の重複レコードを統合する。
    新しいレコードに地域別データが無い場合でも、古い同週レコードの regions を保持する。
    """
    merged = {}
    order = []
    for w in raw_weeks:
        key = (w.get("year"), w.get("week"))
        if key not in merged:
            merged[key] = dict(w)
            order.append(key)
            continue

        base = merged[key]
        for k, v in w.items():
            if k in ("regions", "age_counts", "age_per_sentinel"):
                if isinstance(v, dict) and v:
                    old = base.get(k, {})
                    if isinstance(old, dict):
                        tmp = dict(old)
                        tmp.update(v)
                        base[k] = tmp
                    else:
                        base[k] = dict(v)
            elif v not in (None, "", [], {}):
                base[k] = v
        merged[key] = base

    return sorted((merged[k] for k in order), key=lambda x: (x.get("year", 0), x.get("week", 0)))

def main():
    data=load(HISTORY,{'weeks':[]}); weeks=merge_week_records(data.get('weeks',[]))
    # Safety guard: never silently generate a production report from a truncated/sample history.
    if len(weeks) < 20 and os.environ.get('ALLOW_SHORT_HISTORY') != '1':
        raise RuntimeError(
            f'influenza_history.json has only {len(weeks)} weeks. '
            'Refusing to generate because this looks like sample/truncated data. '
            'Restore the repository production history first.'
        )
    latest=weeks[-1]; prev=weeks[-2] if len(weeks)>1 else {}
    ai=load(AI,{})
    v=float(latest.get('prefecture') or 0); pv=float(prev.get('prefecture') or 0); diff=v-pv
    yoyw=next((x for x in reversed(weeks[:-1]) if x.get('year')==latest.get('year')-1 and x.get('week')==latest.get('week')),None)
    yoy=float(yoyw.get('prefecture')) if yoyw else 0.27
    color,sig,level=signal(v)
    regions=latest.get('regions',{}) or {}; prev_regions=prev.get('regions',{}) or {}
    if prev and not prev_regions:
        print(
            f"[report] warning: previous week {prev.get('year')} W{int(prev.get('week',0)):02d} "
            "has no regional data; regional previous-week cells will be '--'.",
            file=sys.stderr
        )
    display={REGION_DISPLAY.get(k,k):float(val) for k,val in regions.items()}
    top=sorted(display.items(),key=lambda kv:-kv[1])[:5]
    top_rows=''.join(f'<tr><td>{i+1}</td><td>{esc(k)}</td><td>{val:.2f}</td></tr>' for i,(k,val) in enumerate(top))
    counts=latest.get('age_counts',{}) or {}; rates=latest.get('age_per_sentinel',{}) or {}; total=sum(float(counts.get(g,0) or 0) for g in AGE_GROUPS) or 1
    age_headers=''.join(f'<th>{esc(g)}</th>' for g in AGE_GROUPS)
    age_rate=''.join(f'<td>{float(rates.get(g,0) or 0):.2f}</td>' for g in AGE_GROUPS)
    age_count=''.join(f'<td>{int(counts.get(g,0) or 0)}</td>' for g in AGE_GROUPS)
    age_share=''.join(f'<td>{float(counts.get(g,0) or 0)/total*100:.1f}</td>' for g in AGE_GROUPS)
    # region detail follows stable regional order
    reg_headers=''.join(f'<th>{esc(REGION_DISPLAY.get(r,r))}</th>' for r in REGION_ORDER)
    reg_now=''.join(f'<td>{fmt(regions.get(r))}</td>' for r in REGION_ORDER)
    reg_prev=''.join(f'<td>{fmt(prev_regions.get(r))}</td>' for r in REGION_ORDER)
    def delta_cell(r):
        a=regions.get(r); b=prev_regions.get(r)
        return '<td>--</td>' if a is None or b is None else f'<td>{float(a)-float(b):+.2f}</td>'
    reg_diff=''.join(delta_cell(r) for r in REGION_ORDER)
    top1_text=f'{top[0][0]}が {top[0][1]:.2f} 人 / 定点で最も高い。' if top else ''
    agemax=max(AGE_GROUPS,key=lambda g:float(counts.get(g,0) or 0))
    age_top_text=f'{agemax}が {int(counts.get(agemax,0))}人で最多。'
    updated=data.get('meta',{}).get('updated_at') or datetime.now().isoformat()
    try: update=datetime.fromisoformat(updated.replace('Z','+00:00')).strftime('%Y/%m/%d %H:%M')
    except: update=str(updated)
    repl={
      'TITLE_PERIOD':period_text(latest),'UPDATE_TIME':update,'LATEST_VALUE':f'{v:.2f}','PREV_VALUE':f'{pv:.2f}','DIFF_VALUE':f'{diff:+.2f}',
      'SIGNAL_COLOR':color,'SIGNAL_TEXT':sig,'Y_ACTIVE':'active' if level=='yellow' else '','R_ACTIVE':'active' if level=='red' else '','P_ACTIVE':'active' if level=='purple' else '',
      'TREND_SVG':svg_trend(weeks[-6:]),'YOY_VALUE':f'{yoy:.2f}','YOY_DIFF':f'{v-yoy:+.2f}',
      'AI_SUMMARY':esc(ai.get('summary','')),'AI_REGIONAL':esc(ai.get('regional','')),'AI_AGE':esc(ai.get('age_group','')),'AI_YOY':esc(ai.get('year_on_year','')),
      'MAP_HTML':map_html(display),'TOP_REGION_ROWS':top_rows,'AGE_SVG':svg_age(counts,rates),'AGE_HEADERS':age_headers,'AGE_RATE_CELLS':age_rate,'AGE_COUNT_CELLS':age_count,'AGE_SHARE_CELLS':age_share,
      'TOP1_TEXT':esc(top1_text),'AGE_TOP_TEXT':esc(age_top_text),'REGION_HEADERS':reg_headers,'REGION_NOW':reg_now,'REGION_PREV':reg_prev,'REGION_DIFF':reg_diff
    }
    html=TEMPLATE.read_text(encoding='utf-8')
    for k,val in repl.items(): html=html.replace('{{'+k+'}}',str(val))
    rendered=TEMPLATE.parent/'weekly_report_rendered.html'; rendered.write_text(html,encoding='utf-8')
    pdf=OUT/'latest.pdf'
    wp=shutil.which('weasyprint')
    if not wp: raise RuntimeError('weasyprint not found')
    subprocess.run([wp,str(rendered),str(pdf)],check=True)
    print(pdf)

if __name__=='__main__': main()
