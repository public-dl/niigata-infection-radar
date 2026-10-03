"""Regression tests for PDF reporting-week headings (no network or PDF engine)."""
import importlib.util
import json
import re
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('weekly_report', ROOT / 'scripts/generate_weekly_report.py')
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)
TEMPLATE = ROOT / 'reports/template/report.html'


class ReportingWeekTests(unittest.TestCase):
    def render_for_week(self, year, week):
        monday = date.fromisocalendar(year, week, 1)
        weeks = []
        for offset in range(19, -1, -1):
            start = monday - timedelta(weeks=offset)
            end = start + timedelta(days=6)
            iso = start.isocalendar()
            weeks.append({
                'year': iso.year, 'week': iso.week,
                'label': f'R{start.year - 2018}/{start.month}/{start.day}–R{end.year - 2018}/{end.month}/{end.day}',
                'prefecture': 1.0,
                'regions': {region: 1.0 for region in report.REGION_ORDER},
                'age_counts': {age: 1 for age in report.AGE_GROUPS},
                'age_per_sentinel': {age: 0.1 for age in report.AGE_GROUPS},
            })
        # Do not let input order masquerade as correct year/week selection.
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            history = tmp / 'history.json'
            history.write_text(json.dumps({'weeks': list(reversed(weeks))}), encoding='utf-8')
            template = tmp / 'report.html'
            template.write_bytes(TEMPLATE.read_bytes())
            with patch.multiple(report, HISTORY=history, AI=tmp / 'absent-ai.json', TEMPLATE=template, OUT=tmp), \
                 patch.object(report, 'map_html', return_value='<svg></svg>'), \
                 patch.object(report.shutil, 'which', return_value='weasyprint'), \
                 patch.object(report.subprocess, 'run') as pdf:
                report.main()
                pdf.assert_called_once()
            return (tmp / 'weekly_report_rendered.html').read_text(encoding='utf-8')

    def assert_headings(self, year, week):
        html = self.render_for_week(year, week)
        expected = f'{year}年第{week:02d}週'
        title = re.search(r'<span class="period">(.*?)</span>', html).group(1)
        latest = re.search(r'<div class="latest-label">(.*?)</div>', html).group(1)
        region = re.search(r'地域別の状況 <small>(.*?)</small>', html).group(1)
        self.assertTrue(title.startswith(expected + '（'))
        self.assertEqual(latest, f'最新値（{expected}）')
        self.assertEqual(region, f'（{expected}）')
        self.assertNotRegex(html, r'\{\{[A-Z_]+\}\}')
        return html

    def test_regular_week(self):
        html = self.assert_headings(2026, 39)
        # W36 remains valid in the six-week history chart, never in current headings.
        self.assertEqual(html.count('第36週'), 1)

    def test_week_one_starting_in_previous_calendar_year(self):
        html = self.assert_headings(2026, 1)
        self.assertIn('2026年第01週（12/29–R8/1/4）', html)
        self.assertIn('第52週</text>', html)

    def test_week_53(self):
        self.assert_headings(2026, 53)

    def test_week_one_after_week_53(self):
        html = self.assert_headings(2027, 1)
        self.assertIn('第53週</text>', html)

    def test_template_has_no_literal_week_numbers(self):
        self.assertNotRegex(TEMPLATE.read_text(encoding='utf-8'), r'第\s*[0-9０-９]+\s*週')


if __name__ == '__main__':
    unittest.main()
