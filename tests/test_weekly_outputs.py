"""Recovery scenarios with persisted files, mocked API/rendering, and no network."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from weekly_outputs import metadata_path, output_plan, source_week, write_pdf_metadata

spec = importlib.util.spec_from_file_location('recovery_report', ROOT / 'scripts/generate_weekly_report.py')
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.history = self.root / 'history.json'
        self.ai = self.root / 'ai.json'
        self.pdf = self.root / 'latest.pdf'
        self.latest = {'year': 2026, 'week': 39}
        self.write_history()
        self.write_ai(self.latest)
        self.write_pdf(self.latest)

    def write_history(self):
        weeks = [{'year': 2026, 'week': w, 'label': f'2026-W{w}', 'prefecture': 1.0,
                  'regions': {r: 1.0 for r in report.REGION_ORDER},
                  'age_counts': {g: 1 for g in report.AGE_GROUPS},
                  'age_per_sentinel': {g: 0.1 for g in report.AGE_GROUPS}} for w in range(20, 40)]
        self.history.write_text(json.dumps({'weeks': weeks}), encoding='utf-8')

    def write_ai(self, week, summary='unchanged AI prose'):
        self.ai.write_text(json.dumps({'source_week': week, 'summary': summary}), encoding='utf-8')

    def write_pdf(self, week):
        self.pdf.write_bytes(b'%PDF-test-' + str(week).encode())
        write_pdf_metadata(self.pdf, week, self.ai, self.history)

    def plan(self, changed=False):
        return output_plan(self.history, self.ai, self.pdf, changed)

    def cycle(self, changed=False, fail_ai=False, fail_pdf=False):
        """Model the workflow checkpoints: AI is durable before PDF starts."""
        plan = self.plan(changed)
        calls = []
        if plan['generate_ai']:
            calls.append('ai')
            if fail_ai:
                return calls
            self.write_ai(self.latest)
        if plan['generate_pdf']:
            calls.append('pdf')
            if fail_pdf:
                return calls
            self.write_pdf(self.latest)
        return calls

    def test_new_week_generates_both(self):
        old = {'year': 2026, 'week': 38}
        self.write_ai(old)
        self.write_pdf(old)
        self.assertEqual(self.cycle(changed=True), ['ai', 'pdf'])
        self.assertEqual(self.cycle(), [])

    def test_unchanged_history_old_ai_recovers_both(self):
        self.write_ai({'year': 2026, 'week': 38})
        self.assertEqual(self.cycle(), ['ai', 'pdf'])
        self.assertEqual(self.cycle(), [])

    def test_unchanged_history_old_pdf_only(self):
        self.write_pdf({'year': 2026, 'week': 38})
        original_ai = self.ai.read_bytes()
        self.assertEqual(self.cycle(), ['pdf'])
        self.assertEqual(original_ai, self.ai.read_bytes())
        self.assertEqual(self.cycle(), [])

    def test_all_current_does_nothing(self):
        self.assertEqual(self.cycle(), [])

    def test_ai_failure_then_retry_without_data_diff(self):
        self.write_ai({'year': 2026, 'week': 38})
        original_history = self.history.read_bytes()
        self.assertEqual(self.cycle(changed=True, fail_ai=True), ['ai'])
        self.assertEqual(self.history.read_bytes(), original_history)
        self.assertEqual(self.cycle(), ['ai', 'pdf'])
        self.assertEqual(self.cycle(), [])

    def test_pdf_failure_then_retry_does_not_repeat_ai(self):
        old = {'year': 2026, 'week': 38}
        self.write_ai(old)
        self.write_pdf(old)
        original_history = self.history.read_bytes()
        self.assertEqual(self.cycle(changed=True, fail_pdf=True), ['ai', 'pdf'])
        self.assertTrue(self.plan()['ai_current'])
        self.assertFalse(self.plan()['pdf_current'])
        self.assertEqual(self.history.read_bytes(), original_history)
        self.assertEqual(self.cycle(), ['pdf'])
        self.assertEqual(self.cycle(), [])

    def test_missing_ai(self):
        self.ai.unlink()
        self.assertEqual(self.cycle(), ['ai', 'pdf'])

    def test_missing_pdf(self):
        self.pdf.unlink()
        self.assertEqual(self.cycle(), ['pdf'])

    def test_missing_metadata_migrates_once_without_api(self):
        metadata_path(self.pdf).unlink()
        self.assertEqual(self.cycle(), ['pdf'])
        self.assertEqual(self.cycle(), [])

    def test_corrupt_ai_retries(self):
        self.ai.write_text('{', encoding='utf-8')
        self.assertEqual(self.cycle(), ['ai', 'pdf'])

    def test_corrupt_metadata_retries_pdf(self):
        metadata_path(self.pdf).write_text('{', encoding='utf-8')
        self.assertEqual(self.cycle(), ['pdf'])

    def test_pdf_bytes_must_match_metadata(self):
        self.pdf.write_bytes(b'%PDF-different')
        self.assertEqual(self.cycle(), ['pdf'])

    def test_changed_ai_same_week_refreshes_pdf_only(self):
        self.write_ai(self.latest, summary='manual regeneration')
        self.assertEqual(self.cycle(), ['pdf'])

    def test_data_diff_does_not_force_current_ai_api_call(self):
        self.assertEqual(self.cycle(changed=True), ['pdf'])
        self.assertEqual(self.cycle(), [])

    def test_same_week_data_correction_pdf_failure_retries_without_diff(self):
        data = json.loads(self.history.read_text())
        data['weeks'][-1]['prefecture'] = 2.0
        self.history.write_text(json.dumps(data), encoding='utf-8')
        self.assertEqual(self.cycle(changed=True, fail_pdf=True), ['pdf'])
        self.assertEqual(self.cycle(), ['pdf'])
        self.assertEqual(self.cycle(), [])

    def test_reporting_year_is_compared(self):
        self.write_ai({'year': 2025, 'week': 39})
        self.assertTrue(self.plan()['generate_ai'])

    def test_invalid_history_fails_closed(self):
        original_pdf = self.pdf.read_bytes()
        for value in ('{}', '{', '{"weeks":[{"year":2026,"week":0}]}'):
            with self.subTest(value=value):
                self.history.write_text(value, encoding='utf-8')
                with self.assertRaises(ValueError):
                    self.plan()
        self.assertEqual(original_pdf, self.pdf.read_bytes())

    def test_week_normalization(self):
        self.assertEqual(source_week({'year': '2027', 'week': '01'}), (2027, 1))
        self.assertIsNone(source_week({'year': 2027, 'week': True}))
        self.assertIsNone(source_week({'year': 2027, 'week': 1.5}))

    def run_generator(self, renderer):
        template = self.root / 'report.html'
        template.write_bytes((ROOT / 'reports/template/report.html').read_bytes())
        with patch.multiple(report, HISTORY=self.history, AI=self.ai, TEMPLATE=template, OUT=self.root), \
             patch.object(report, 'map_html', return_value='<svg></svg>'), \
             patch.object(report.shutil, 'which', return_value='weasyprint'), \
             patch.object(report.subprocess, 'run', side_effect=renderer):
            report.main()

    def test_generator_success_publishes_pdf_and_metadata(self):
        self.write_pdf({'year': 2026, 'week': 38})
        self.run_generator(lambda command, **kw: Path(command[2]).write_bytes(b'%PDF-generated'))
        self.assertFalse(self.plan()['generate_pdf'])
        self.assertFalse(self.pdf.with_suffix('.pending.pdf').exists())

    def test_renderer_partial_failure_preserves_previous_pdf_and_metadata(self):
        self.write_pdf({'year': 2026, 'week': 38})
        old_pdf, old_meta = self.pdf.read_bytes(), metadata_path(self.pdf).read_bytes()
        def fail(command, **kwargs):
            Path(command[2]).write_bytes(b'%PDF-partial')
            raise subprocess.CalledProcessError(1, command)
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_generator(fail)
        self.assertEqual(self.pdf.read_bytes(), old_pdf)
        self.assertEqual(metadata_path(self.pdf).read_bytes(), old_meta)
        self.assertFalse(self.pdf.with_suffix('.pending.pdf').exists())
        self.assertEqual(self.cycle(), ['pdf'])

    def test_renderer_empty_success_is_rejected(self):
        self.write_pdf({'year': 2026, 'week': 38})
        with self.assertRaises(RuntimeError):
            self.run_generator(lambda command, **kw: Path(command[2]).write_bytes(b''))
        self.assertTrue(self.plan()['generate_pdf'])

    def test_interrupted_metadata_write_is_detected_next_time(self):
        with patch.object(report, 'write_pdf_metadata', side_effect=OSError('disk error')):
            with self.assertRaises(OSError):
                self.run_generator(lambda command, **kw: Path(command[2]).write_bytes(b'%PDF-new'))
        self.assertEqual(self.cycle(), ['pdf'])

    def test_real_ai_entry_point_failure_retry_and_same_week_skip(self):
        # Stub only the external SDK import and API call, not the script's file logic.
        fake_sdk = types.ModuleType('openai')
        fake_sdk.OpenAI = lambda: self.fail('Unexpected live API client')
        ai_spec = importlib.util.spec_from_file_location('test_ai_generator', ROOT / 'scripts/generate_ai_comment.py')
        ai_module = importlib.util.module_from_spec(ai_spec)
        with patch.dict(sys.modules, {'openai': fake_sdk}):
            ai_spec.loader.exec_module(ai_module)
        self.write_ai({'year': 2026, 'week': 38})
        old_ai, history = self.ai.read_bytes(), self.history.read_bytes()
        with patch.multiple(ai_module, HISTORY_PATH=self.history, OUTPUT_PATH=self.ai, FORCE=False), \
             patch.dict(ai_module.os.environ, {'OPENAI_API_KEY': 'local-test-only'}):
            with patch.object(ai_module, 'generate_comment', side_effect=RuntimeError('API unavailable')):
                with self.assertRaises(RuntimeError):
                    ai_module.main()
            self.assertEqual(self.ai.read_bytes(), old_ai)
            self.assertEqual(self.history.read_bytes(), history)
            self.assertTrue(self.plan()['generate_ai'])
            result = {key: 'test text' for key in ai_module.REQUIRED_FIELDS}
            result['emphasis'] = []
            with patch.object(ai_module, 'generate_comment', return_value=result) as generate:
                ai_module.main()
                generate.assert_called_once()
            self.assertTrue(self.plan()['ai_current'])
            with patch.object(ai_module, 'generate_comment') as generate:
                ai_module.main()
                generate.assert_not_called()

    def test_cli_outputs_and_verification(self):
        cli = [sys.executable, '-B', str(ROOT / 'scripts/weekly_outputs.py'),
               '--history', str(self.history), '--ai', str(self.ai), '--pdf', str(self.pdf)]
        output = self.root / 'github-output'
        run = subprocess.run(cli + ['--github-output', str(output), '--require-current'], capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('generate_ai=false', output.read_text())
        self.assertIn('generate_pdf=false', output.read_text())
        self.pdf.unlink()
        self.assertNotEqual(subprocess.run(cli + ['--require-current'], capture_output=True).returncode, 0)
        self.assertEqual(subprocess.run(cli + ['--require-ai'], capture_output=True).returncode, 0)


if __name__ == '__main__':
    unittest.main()
