"""Reject stale completion logs while allowing short current runs to finish."""
import unittest
from cfd_studio.solver_status import current_log_finished


class SolverStatusTests(unittest.TestCase):
    def test_current_short_run_completes_without_freshness_delay(self):
        self.assertTrue(current_log_finished('Time = 60\nEnd\n', 'new', 'new', 100.2, 100.1, 0))

    def test_old_or_running_logs_cannot_complete_a_new_case(self):
        for args in [
            ('End', 'old', 'new', 101, 100, 0),
            ('End', 'new', 'new', 99, 100, 0),
            ('End', 'new', 'new', 101, 100, 1),
            ('Time = 60', 'new', 'new', 101, 100, 0),
            ('End', 'new', 'new', 'nan', 100, 0),
            ('End', 'new', 'new', 101, None, 0),
        ]:
            self.assertFalse(current_log_finished(*args))


class FramePolicyTests(unittest.TestCase):
    def test_initial_frame_policy_preserves_legacy_and_explicit_inclusion(self):
        from cfd_studio.frame_policy import selected_output_times
        times = ['0', '20', '40']
        for config in ({}, {'_studio': {'termination': {'include_initial': True}}}):
            self.assertEqual(selected_output_times(times, config), times)
        self.assertEqual(selected_output_times(times, {'_studio': {'termination': {'include_initial': False}}}), ['20', '40'])
        self.assertEqual(times, ['0', '20', '40'])
