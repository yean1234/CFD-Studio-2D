import unittest
from unittest.mock import Mock

from cfd_studio.execution_workspace import ExecutionWorkspace


class CaseResultProgressTests(unittest.TestCase):
    def workspace(self, states):
        workspace = ExecutionWorkspace.__new__(ExecutionWorkspace)
        records = {key: {'id': key, 'path': key, 'result_status': 'none'} for key in states}
        records['other'] = {'id': 'other', 'path': 'other', 'result_status': 'ready'}
        workspace.discover = Mock(return_value=records)
        workspace._catalog = Mock(return_value={'projects': [{'id': 'project', 'runs': list(states)}]})
        def info(record):
            value = states[record['id']]
            if isinstance(value, Exception):
                raise value
            return value
        workspace.result_info = Mock(side_effect=info)
        return workspace

    def test_saved_results_fill_immediately_and_unstarted_results_stay_empty(self):
        w = self.workspace({'ready': {'result_status': 'ready'}, 'empty': {}})
        rows = w.result_progress('project')['runs']
        self.assertEqual([r['percent'] for r in rows], [100, 0])
        self.assertEqual([r['active'] for r in rows], [False, False])
        self.assertEqual(w.result_info.call_count, 2)

    def test_progress_counts_successful_conversions_not_attempts(self):
        w = self.workspace({'working': {'result_status': 'preparing',
            'extract': {'busy': True, 'total': 10, 'done': 3, 'processed': 9}}})
        row = w.result_progress('project')['runs'][0]
        self.assertEqual(row['percent'], 30)
        self.assertTrue(row['active'])

    def test_unknown_totals_do_not_invent_a_percentage(self):
        w = self.workspace({'working': {'result_status': 'preparing', 'extract': {'busy': True}},
                            'new': {'result_status': 'update'}})
        rows = w.result_progress('project')['runs']
        self.assertEqual([r['percent'] for r in rows], [None, None])
        self.assertEqual([r['active'] for r in rows], [True, False])

    def test_in_progress_or_failed_work_never_reports_complete(self):
        w = self.workspace({'working': {'result_status': 'preparing', 'extract': {'busy': True, 'total': 4, 'done': 4}},
            'failed': {'result_status': 'update', 'extract': {'total': 4, 'done': 4, 'failed': 1, 'last_error': 'bad frame'}}})
        rows = w.result_progress('project')['runs']
        self.assertEqual([r['percent'] for r in rows], [99, 99])
        self.assertEqual(rows[1]['error'], 'bad frame')

    def test_a_broken_case_does_not_hide_other_results(self):
        w = self.workspace({'broken': OSError('unavailable'), 'ready': {'result_status': 'ready'}})
        rows = w.result_progress('project')['runs']
        self.assertEqual(rows[0]['label'], '확인 실패')
        self.assertEqual(rows[1]['percent'], 100)
        with self.assertRaises(ValueError):
            w.result_progress('other-project')
