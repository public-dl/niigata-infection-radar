"""Offline SEO publishing and recovery regression tests."""
import copy
from datetime import date, timedelta
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import update_seo as seo
from test_workflow_recovery import steps


class SeoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'data').mkdir()
        self.html = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.html = re.sub(seo.MARKER, '', self.html)
        (self.root / 'index.html').write_text(self.html, encoding='utf-8')
        self.xml = (ROOT / 'sitemap.xml').read_text(encoding='utf-8')
        (self.root / 'sitemap.xml').write_text(self.xml, encoding='utf-8')
        self.history = {'meta': {'updated_at': '2026-11-05T19:59:23+09:00'}, 'weeks': []}
        for year, week, rate in [(2025,44,4.15),(2026,43,11.4),(2026,44,13.44)]:
            start = date.fromisocalendar(year, week, 1)
            self.history['weeks'].append({
                'year':year, 'week':week, 'start':start.isoformat(),
                'end':(start+timedelta(days=6)).isoformat(), 'prefecture':rate,
                'regions':{'佐渡':38.0,'村上':22.0,'南魚沼':17.0,'新潟市':14.94},
                'age_per_sentinel':{'0歳':0.16,'5～9歳':3.42,'10～14歳':2.8},
                'source_page':'https://www.pref.niigata.lg.jp/sec/kanyaku/shuho0844.html',
            })
        self.ai = {'source_week':{'year':2026,'week':44}, 'summary':'報告数は13.44人/定点で、前週から増加しました。'}
        self.save()

    def save(self):
        for name, obj in [('influenza_history', self.history), ('ai_comment', self.ai)]:
            (self.root / f'data/{name}.json').write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')

    def output(self):
        return (self.root / 'index.html').read_text(encoding='utf-8')

    def blobs(self):
        return [(self.root / p).read_bytes() for p in ['index.html', 'sitemap.xml']]

    def test_current_data_visible_without_javascript(self):
        self.assertTrue(seo.update(self.root))
        html = self.output()
        section = re.search(r'<section class="card" id="weekly-static-summary".*?</section>', html, re.S)[0]
        for text in ['2026年第44週', '2026-10-26', '2026-11-01', '13.44', '11.40', '2.04', '4.15', '佐渡', '村上', '南魚沼', '5～9歳', '3.42', self.ai['summary'], '2026-11-05']:
            self.assertIn(text, section)
        self.assertNotRegex(section, r'display\s*:\s*none|\bhidden\b|<script')

    def test_metadata_title_and_website_preserved(self):
        seo.update(self.root)
        html = self.output()
        for attr in ['name="description"', 'property="og:description"', 'name="twitter:description"']:
            meta = re.search(r'<meta ' + attr + r'[^>]+>', html)[0]
            for text in ['2026年第44週', '13.44', '2.04', '地域別', '年代別', '時系列']:
                self.assertIn(text, meta)
        self.assertEqual(re.search(r'<title>.*?</title>', html)[0], re.search(r'<title>.*?</title>', self.html)[0])
        datasets = [json.loads(s) for s in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
        self.assertEqual([d['@type'] for d in datasets], ['WebSite', 'Dataset'])
        website_before = json.loads(re.findall(r'<script type="application/ld\+json">(.*?)</script>', self.html, re.S)[0])
        self.assertEqual(datasets[0], website_before)
        self.assertEqual(datasets[1]['dateModified'], '2026-11-05')
        self.assertEqual(datasets[1]['spatialCoverage']['name'], '新潟県')

    def test_sitemap_changes_homepage_only(self):
        seo.update(self.root)
        xml = (self.root / 'sitemap.xml').read_text(encoding='utf-8')
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        old, new = ET.fromstring(self.xml), ET.fromstring(xml)
        self.assertEqual(ET.tostring(old[1]), ET.tostring(new[1]))
        self.assertEqual(new[0].findtext('s:lastmod', namespaces=ns), '2026-11-05')

    def test_unchanged_history_is_byte_and_mtime_noop_even_if_ai_changed(self):
        seo.update(self.root)
        before = self.blobs()
        mtimes = [(self.root / n).stat().st_mtime_ns for n in ['index.html', 'sitemap.xml']]
        self.ai['summary'] = '同じ週のAIだけを再生成'
        self.save()
        self.assertFalse(seo.update(self.root))
        self.assertEqual(before, self.blobs())
        self.assertEqual(mtimes, [(self.root / n).stat().st_mtime_ns for n in ['index.html', 'sitemap.xml']])

    def advance(self, year, week):
        latest = copy.deepcopy(max(self.history['weeks'], key=lambda w:(w['year'], w['week'])))
        start = date.fromisocalendar(year, week, 1)
        latest.update(year=year, week=week, start=start.isoformat(), end=(start+timedelta(days=6)).isoformat(), prefecture=15.44)
        self.history['weeks'].append(latest)
        self.history['meta']['updated_at'] = (start+timedelta(days=10)).isoformat()+'T10:00:00+09:00'
        self.ai['source_week'] = {'year':year, 'week':week}
        self.ai['summary'] = f'{year}年第{week}週の要約'
        self.save()

    def test_new_week_updates_and_then_skips(self):
        seo.update(self.root)
        self.advance(2026, 45)
        self.assertTrue(seo.update(self.root))
        self.assertIn('2026年第45週', self.output())
        self.assertIn('15.44', self.output())
        self.assertIn('2.00人/定点増加', self.output())
        self.assertIn('2026-11-12', (self.root/'sitemap.xml').read_text())
        self.assertFalse(seo.update(self.root))

    def test_same_week_data_correction_updates(self):
        seo.update(self.root)
        max(self.history['weeks'], key=lambda w:(w['year'],w['week']))['prefecture'] = 12.4
        self.save()
        self.assertTrue(seo.update(self.root))
        self.assertIn('12.40', self.output())

    def test_json_formatting_only_does_not_republish(self):
        seo.update(self.root)
        before = self.blobs()
        (self.root/'data/influenza_history.json').write_text(
            json.dumps(self.history, ensure_ascii=False, indent=4), encoding='utf-8', newline='\r\n')
        self.assertFalse(seo.update(self.root))
        self.assertEqual(before, self.blobs())

    def test_ai_failure_is_non_mutating_then_retry_after_data_commit(self):
        seo.update(self.root)
        self.advance(2026,45)
        self.ai['source_week']['week'] = 44
        self.save()
        before = self.blobs()
        with self.assertRaises(ValueError):
            seo.update(self.root)
        self.assertEqual(before,self.blobs())
        self.ai['source_week']['week'] = 45
        self.save()
        self.assertTrue(seo.update(self.root))

    def test_interrupted_html_write_retries_after_sitemap_write(self):
        seo.update(self.root)
        self.advance(2026,45)
        original = Path.write_text
        def fail_html(path, *args, **kwargs):
            if path.name == 'index.html':
                raise OSError('simulated interruption')
            return original(path, *args, **kwargs)
        with patch.object(Path,'write_text',fail_html), self.assertRaises(OSError):
            seo.update(self.root)
        self.assertTrue(seo.update(self.root))
        self.assertFalse(seo.update(self.root))

    def test_year_boundary_uses_previous_iso_week(self):
        self.advance(2026,53)
        self.advance(2027,1)
        seo.update(self.root)
        self.assertIn('2027年第1週', self.output())
        self.assertIn('前週値は15.44', self.output())
        self.assertIn('前週と同じ', self.output())

    def test_missing_previous_week_is_not_previous_available_week(self):
        self.advance(2027,2)
        seo.update(self.root)
        self.assertIn('前週値・前週比は未確認', self.output())
        self.assertIn('前年同週', self.output())

    def test_zero_decrease_and_tied_age_values(self):
        latest=max(self.history['weeks'],key=lambda w:(w['year'],w['week']))
        latest['prefecture']=0
        latest['age_per_sentinel']={'0歳':0,'1～4歳':0}
        self.save()
        seo.update(self.root)
        self.assertIn('11.40人/定点減少', self.output())
        self.assertIn('0歳・1～4歳（0.00', self.output())

    def test_escapes_ai_text_and_keeps_json_valid(self):
        self.ai['summary'] = '</script><img src=x onerror="bad()"> & test'
        self.save()
        seo.update(self.root)
        self.assertNotIn('<img src=x', self.output())
        self.assertIn('&lt;img', self.output())

    def test_invalid_sitemap_changes_nothing(self):
        (self.root/'sitemap.xml').write_text('<broken>')
        before=self.blobs()
        with self.assertRaises(ET.ParseError):
            seo.update(self.root)
        self.assertEqual(before,self.blobs())

    def test_workflow_seo_runs_after_verification_and_commits_both_files(self):
        for name in ['update-influenza.yml','generate_weekly_outputs.yml']:
            st=steps(name)
            names=[s.get('name') for s in st]
            seo_step=st[names.index('Update static weekly SEO')]
            self.assertNotIn('if',seo_step)
            self.assertLess(names.index('Verify weekly outputs'),names.index('Update static weekly SEO'))
            commit=st[names.index('Commit PDF and metadata')]
            self.assertIn("steps.seo.outputs.changed == 'true'",commit['if'])
            self.assertIn('git add index.html sitemap.xml',commit['run'])
            self.assertNotIn('git add .',commit['run'])


if __name__ == '__main__':
    unittest.main()
