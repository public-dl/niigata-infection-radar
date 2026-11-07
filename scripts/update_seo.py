"""Publish a visible weekly snapshot without changing the client-side application.

The embedded history digest is a completion marker: unchanged data is a byte-for-
byte no-op, while data committed before a failed AI/PDF/SEO run can be retried.
No clock, network, AI API or PDF renderer is used here.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from html import escape
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from weekly_outputs import source_week

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://public-dl.github.io/niigata-infection-radar/'
START, END = '<!-- WEEKLY-SEO:START -->', '<!-- WEEKLY-SEO:END -->'
DS_START, DS_END = '<!-- WEEKLY-DATASET:START -->', '<!-- WEEKLY-DATASET:END -->'
MARKER = r'<!-- WEEKLY-SEO-HISTORY:([a-f0-9]{64}) -->'
JST = timezone(timedelta(hours=9))


def number(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError('Boolean is not a report value')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Invalid report value') from exc
    if not result.is_finite() or result < 0:
        raise ValueError('Report values must be finite and non-negative')
    return result


def replace_once(text, pattern, replacement):
    result, count = re.subn(pattern, lambda _: replacement, text, flags=re.S)
    if count != 1:
        raise ValueError(f'Expected one HTML/XML target, found {count}: {pattern}')
    return result


def block(text, start, end, content, anchor):
    replacement = f'{start}\n{content}\n{end}'
    if start in text or end in text:
        return replace_once(text, re.escape(start) + '.*?' + re.escape(end), replacement)
    return replace_once(text, re.escape(anchor), replacement + '\n' + anchor)


def sitemap_update(xml, updated):
    ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    root = ET.fromstring(xml)
    targets = [u for u in root.findall('s:url', ns) if u.findtext('s:loc', namespaces=ns) == URL]
    if len(targets) != 1 or targets[0].find('s:lastmod', ns) is None:
        raise ValueError('Sitemap must contain one homepage with lastmod')
    # Preserve unrelated URL timestamps and XML formatting.
    pattern = r'<url>\s*<loc>' + re.escape(URL) + r'</loc>.*?</url>'
    entry = re.search(pattern, xml, re.S)
    if not entry:
        raise ValueError('Unsupported sitemap layout')
    replacement = replace_once(entry.group(), r'<lastmod>.*?</lastmod>', f'<lastmod>{updated}</lastmod>')
    return replace_once(xml, pattern, replacement)


def build(html, xml, history, ai, digest):
    weeks = history['weeks']
    keys = [source_week(w) for w in weeks]
    if not weeks or any(k is None for k in keys) or len(set(keys)) != len(keys):
        raise ValueError('History must contain unique valid reporting weeks')
    by_week = dict(zip(keys, weeks))
    key = max(by_week)
    latest = by_week[key]
    if source_week(ai.get('source_week')) != key:
        raise ValueError('AI week must match latest data before publishing SEO')
    start, end = date.fromisoformat(latest['start']), date.fromisoformat(latest['end'])
    if end < start or start.isocalendar()[:2] != key:
        raise ValueError('Reporting dates do not match reporting week')
    previous_key = (start - timedelta(days=7)).isocalendar()[:2]
    current = number(latest['prefecture'])
    if current is None:
        raise ValueError('Latest prefecture value is missing')
    previous = number(by_week.get(previous_key, {}).get('prefecture'))
    prior_year = number(by_week.get((key[0] - 1, key[1]), {}).get('prefecture'))
    if previous is None:
        change = '前週値・前週比は未確認です。'
    else:
        delta = current - previous
        change = ('前週と同じです。' if delta == 0 else
                  f'前週から{abs(delta):.2f}人/定点{"増加" if delta > 0 else "減少"}しています。')
    label = f'{key[0]}年第{key[1]}週'
    description = (f'{label}の新潟県インフルエンザ定点当たり報告数は{current:.2f}人/定点。'
                   f'{change}地域別マップ、年代別、時系列、前年同期比較で流行状況を確認できます。')
    updated_dt = datetime.fromisoformat(history['meta']['updated_at'].replace('Z', '+00:00'))
    if updated_dt.tzinfo is None:
        raise ValueError('History updated_at must include timezone')
    updated = updated_dt.astimezone(JST).date().isoformat()
    regions = [(name, number(v)) for name, v in latest.get('regions', {}).items()]
    regions = sorted(((n, v) for n, v in regions if v is not None), key=lambda x: (-x[1], x[0]))[:3]
    region_text = ('地域別の上位は、' + '、'.join(f'{n}{v:.2f}人/定点' for n, v in regions) + 'です。'
                   if regions else '地域別の数値は未確認です。')
    ages = [(name, number(v)) for name, v in latest.get('age_per_sentinel', {}).items()]
    ages = [(n, v) for n, v in ages if v is not None]
    if ages:
        peak = max(v for _, v in ages)
        names = '・'.join(n for n, v in ages if v == peak)
        age_text = f'年代別の定点当たり報告数が最も高いのは{names}（{peak:.2f}人/定点）です。'
    else:
        age_text = '年代別の数値は未確認です。'
    summary = ai.get('summary')
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError('AI summary is missing')
    source = latest['source_page']
    if not source.startswith('https://www.pref.niigata.lg.jp/'):
        raise ValueError('Expected official Niigata source URL')
    previous_text = f'前週値は{previous:.2f}人/定点です。' if previous is not None else ''
    yoy = (f'前年同週（{key[0]-1}年第{key[1]}週）は{prior_year:.2f}人/定点でした。'
           if prior_year is not None else '前年同週の数値は未確認です。')
    paragraphs = [f'{label}（{start.isoformat()}～{end.isoformat()}）の新潟県の定点当たり報告数は{current:.2f}人/定点でした。{previous_text}{change}{yoy}',
                  region_text + '地域は報告医療機関の所在地に基づきます。',
                  age_text + '年齢幅や受診状況が異なるため、年代間の感染リスクの比較ではありません。',
                  'AI週次要約：' + summary.strip()]
    snapshot = '<section class="card" id="weekly-static-summary" aria-labelledby="weekly-static-title">\n'
    snapshot += '  <h2 id="weekly-static-title">最新週のデータ概要</h2>\n'
    snapshot += ''.join(f'  <p>{escape(p)}</p>\n' for p in paragraphs)
    snapshot += f'  <p class="muted small">データ最終更新日：<time datetime="{updated}">{updated}</time> ／ <a href="{escape(source, quote=True)}">新潟県感染症情報（週報）：{label}</a></p>\n</section>'
    snapshot += f'\n<!-- WEEKLY-SEO-HISTORY:{digest} -->'
    html = block(html, START, END, snapshot, '<section class="footer-note" id="about">')
    for attribute in ('name="description"', 'property="og:description"', 'name="twitter:description"'):
        html = replace_once(html, r'<meta ' + re.escape(attribute) + r' content="[^"]*"\s*/?>',
                            f'<meta {attribute} content="{escape(description, quote=True)}" />')
    dataset = {
        '@context': 'https://schema.org', '@type': 'Dataset', '@id': URL + '#weekly-dataset',
        'name': '新潟県インフルエンザ週次公表データ', 'description': description + '新潟県感染症情報（週報）を元に地域別・年代別・時系列で整理したデータです。',
        'url': URL, 'version': label, 'dateModified': updated,
        'temporalCoverage': min(w['start'] for w in weeks) + '/' + end.isoformat(),
        'spatialCoverage': {'@type': 'Place', 'name': '新潟県'},
        'isBasedOn': {'@type': 'CreativeWork', 'name': '新潟県感染症情報（週報）', 'url': source},
        'publisher': {'@type': 'Organization', 'name': 'CivITech'},
        'variableMeasured': 'インフルエンザ定点当たり報告数（人/定点）',
        'distribution': {'@type': 'DataDownload', 'encodingFormat': 'application/json', 'contentUrl': URL + 'data/influenza_history.json'},
        'inLanguage': 'ja',
    }
    encoded = json.dumps(dataset, ensure_ascii=False, indent=2).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    html = block(html, DS_START, DS_END, '<script type="application/ld+json">\n' + encoded + '\n</script>', '</head>')
    return html, sitemap_update(xml, updated)


def update(root=ROOT):
    root = Path(root)
    history_bytes = (root / 'data/influenza_history.json').read_bytes()
    history = json.loads(history_bytes)
    # Git may convert LF/CRLF on Windows; only data changes should republish.
    canonical = json.dumps(history, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    html_path, xml_path = root / 'index.html', root / 'sitemap.xml'
    html, xml = html_path.read_text(encoding='utf-8'), xml_path.read_text(encoding='utf-8')
    # The same history does not republish timestamps, even after an AI-only run.
    marker = re.search(MARKER, html)
    if marker and marker[1] == digest:
        expected = datetime.fromisoformat(history['meta']['updated_at'].replace('Z', '+00:00')).astimezone(JST).date().isoformat()
        if sitemap_update(xml, expected) == xml:
            return False
    ai = json.loads((root / 'data/ai_comment.json').read_text(encoding='utf-8'))
    new_html, new_xml = build(html, xml, history, ai, digest)
    # Validate both outputs before writing. Marker is written last so interruption
    # between files is recoverable on the next run.
    ET.fromstring(new_xml)
    if new_xml != xml:
        xml_path.write_text(new_xml, encoding='utf-8', newline='\n')
    if new_html != html:
        html_path.write_text(new_html, encoding='utf-8', newline='\n')
    return new_html != html or new_xml != xml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--github-output', type=Path)
    args = parser.parse_args()
    changed = update(args.root)
    print('SEO snapshot updated.' if changed else 'SEO snapshot current; no files changed.')
    if args.github_output:
        with args.github_output.open('a', encoding='utf-8') as stream:
            stream.write(f'changed={str(changed).lower()}\n')


if __name__ == '__main__':
    main()
