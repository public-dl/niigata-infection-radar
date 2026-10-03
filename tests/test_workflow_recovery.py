"""Guard recovery conditions, commit boundaries, and the shared writer lock."""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / '.github/workflows'
WRITERS = ['update-influenza.yml', 'generate_weekly_outputs.yml', 'generate-weekly-report.yml',
           'generate_ai_comment.yml', 'backfill-influenza.yml']


def workflow(name):
    return yaml.load((WORKFLOWS / name).read_text(encoding='utf-8'), Loader=yaml.BaseLoader)


def steps(name):
    return next(iter(workflow(name)['jobs'].values()))['steps']


class WorkflowRecoveryTests(unittest.TestCase):
    def test_all_writers_share_branch_lock_and_checkout_current_branch(self):
        for name in WRITERS:
            with self.subTest(workflow=name):
                wf = workflow(name)
                self.assertEqual(wf['concurrency']['group'], 'influenza-repository-writer-${{ github.ref }}')
                self.assertEqual(wf['concurrency']['cancel-in-progress'], 'false')
                checkout = next(s for s in steps(name) if s.get('uses', '').startswith('actions/checkout@'))
                self.assertEqual(checkout['with']['ref'], '${{ github.ref_name }}')

    def test_schedule_and_manual_entry_points_are_preserved(self):
        wf = workflow('update-influenza.yml')
        self.assertEqual([x['cron'] for x in wf['on']['schedule']], ['17 3,6,9 * * 4,5', '17 9 * * 1-3'])
        for name in WRITERS:
            self.assertIn('workflow_dispatch', workflow(name)['on'])

    def test_data_commit_precedes_recovery_and_ai_commit_precedes_pdf(self):
        st = steps('update-influenza.yml')
        names = [s.get('name') for s in st]
        self.assertLess(names.index('Commit and push data first'), names.index('Plan weekly output recovery'))
        self.assertLess(names.index('Commit AI before PDF generation'), names.index('Generate weekly PDF'))
        self.assertNotIn('if', st[names.index('Plan weekly output recovery')])
        for name, output in [('Generate AI weekly insight', 'generate_ai'), ('Generate weekly PDF', 'generate_pdf')]:
            self.assertEqual(st[names.index(name)]['if'], f"steps.output_plan.outputs.{output} == 'true'")
        self.assertIn('scripts/weekly_outputs.py --require-current', st[names.index('Verify weekly outputs')]['run'])

    def test_pdf_and_metadata_are_committed_together_everywhere(self):
        for name in WRITERS[:3]:
            commits = [s for s in steps(name) if 'git add reports/latest.pdf' in s.get('run', '')]
            self.assertEqual(len(commits), 1, name)
            self.assertIn('git add reports/latest.pdf reports/latest.meta.json', commits[0]['run'])
            self.assertNotIn('git add .', commits[0]['run'])

    def test_manual_force_and_pdf_only_generation_still_work(self):
        st = steps('generate_weekly_outputs.yml')
        ai = next(s for s in st if s.get('name') == 'Generate AI weekly insight')
        pdf = next(s for s in st if s.get('name') == 'Generate A4 landscape PDF')
        for step in (ai, pdf):
            self.assertIn("github.event.inputs.force_regenerate == 'true'", step['if'])
        names = [s.get('name') for s in st]
        self.assertLess(names.index('Commit AI before PDF generation'), names.index('Generate A4 landscape PDF'))
        pdf_only = next(s for s in steps('generate-weekly-report.yml') if s.get('name') == 'Generate PDF')
        self.assertNotIn('if', pdf_only)


if __name__ == '__main__':
    unittest.main()
