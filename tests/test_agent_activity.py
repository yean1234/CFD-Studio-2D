"""Progress receipts must never authorize or execute CFD operations."""
import io
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from cfd_studio.agent_activity import Activity, ActivityError, route
from cfd_studio.agent_progress import main, request


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.activity = Activity(clock=lambda: self.now, wall=lambda: self.now, ttl=120)

    def start(self):
        return self.activity.dispatch({'action': 'start', 'name': 'Agent', 'mode': 'development',
                                       'stage': 'debug', 'detail': 'Checking progress delivery'})

    def test_claim_token_private_and_other_owner_rejected(self):
        owner = self.start()
        self.assertNotIn('token', self.activity.snapshot())
        with self.assertRaisesRegex(ActivityError, 'ACTIVITY_BUSY'):
            self.start()
        with self.assertRaisesRegex(ActivityError, 'OWNER_MISMATCH'):
            self.activity.dispatch({'action': 'update', 'token': 'other', 'stage': 'debug', 'detail': 'Change'})
        self.assertEqual(owner['task'], self.activity.snapshot()['task'])

    def test_user_pause_blocks_updates_new_claims_and_survives_expiry(self):
        owner = self.start()
        self.activity.dispatch({'action': 'pause'})
        self.now = 130
        for body in ({'action': 'start'}, {'action': 'update', 'token': owner['token']}):
            with self.assertRaisesRegex(ActivityError, 'PAUSED'):
                self.activity.dispatch(body)
        self.assertEqual(self.activity.snapshot()['task']['status'], 'paused')
        self.activity.dispatch({'action': 'resume'})
        self.assertEqual(self.activity.snapshot()['task']['status'], 'disconnected')

    def test_expired_replacement_invalidates_old_owner(self):
        owner = self.start()
        self.now = 121
        self.assertEqual(self.activity.snapshot()['task']['status'], 'disconnected')
        replacement = self.start()
        self.assertNotEqual(owner['token'], replacement['token'])
        with self.assertRaisesRegex(ActivityError, 'OWNER_MISMATCH'):
            self.activity.dispatch({'action': 'finish', 'token': owner['token'], 'stage': 'completed', 'detail': 'Done'})

    def test_display_receipt_expires_and_new_revision_needs_fresh_render(self):
        owner = self.start()
        self.assertFalse(owner['displayed'])
        self.activity.dispatch({'action': 'seen', 'tab': 'visible-tab', 'revision': owner['revision']})
        self.assertTrue(self.activity.snapshot()['displayed'])
        update = self.activity.dispatch({'action': 'update', 'token': owner['token'], 'stage': 'test', 'detail': 'Running tests'})
        self.assertFalse(update['displayed'])
        with self.assertRaisesRegex(ActivityError, 'STALE'):
            self.activity.dispatch({'action': 'seen', 'tab': 'visible-tab', 'revision': owner['revision']})
        self.activity.dispatch({'action': 'seen', 'tab': 'visible-tab', 'revision': update['revision']})
        self.now = 9
        self.assertFalse(self.activity.snapshot()['displayed'])

    def test_finish_does_not_resume_and_finished_owner_cannot_mutate(self):
        owner = self.start()
        self.activity.dispatch({'action': 'pause'})
        result = self.activity.dispatch({'action': 'finish', 'token': owner['token'], 'stage': 'completed', 'detail': 'Tests completed'})
        self.assertTrue(result['paused'])
        with self.assertRaisesRegex(ActivityError, 'FINISHED'):
            self.activity.dispatch({'action': 'update', 'token': owner['token'], 'stage': 'test', 'detail': 'More'})

    def test_invalid_payloads_do_not_mutate_owner_or_history(self):
        for body in ([], {'action': 'execute'}, {'action': 'start', 'name': 'agent', 'mode': 'development', 'stage': [], 'detail': 'x'}):
            with self.assertRaises(ActivityError):
                self.activity.dispatch(body)
        self.assertIsNone(self.activity.snapshot()['task'])

    def test_history_bounded_and_snapshots_are_independent(self):
        owner = self.start()
        for i in range(25):
            self.activity.dispatch({'action': 'update', 'token': owner['token'], 'stage': 'test', 'detail': str(i)})
        state = self.activity.snapshot()
        self.assertEqual(len(state['history']), 20)
        state['task']['detail'] = 'changed'
        state['history'][0]['detail'] = 'changed'
        self.assertNotEqual(self.activity.snapshot()['history'][0]['detail'], 'changed')
        self.assertEqual(self.activity.snapshot()['task']['detail'], '24')


class RouteTests(unittest.TestCase):
    def call(self, body=None, **headers):
        class Handler:
            path = '/api/agent/activity'
            client_address = ('127.0.0.1', 123)
            def _json(self, value, code=200):
                self.value, self.code = value, code
        handler = Handler()
        raw = json.dumps(body).encode()
        handler.headers = {'Host': '127.0.0.1:8712', 'Content-Type': 'application/json',
                           'Content-Length': str(len(raw)), 'X-CFD-Activity': '1', **headers}
        handler.rfile = io.BytesIO(raw)
        route(handler, post=body is not None, activity=Activity())
        return handler

    def test_cross_origin_and_rebinding_rejected(self):
        for headers in ({'Origin': 'https://other.example'}, {'Host': 'evil.example:8712'},
                        {'Sec-Fetch-Site': 'cross-site'}):
            self.assertEqual(self.call({'action': 'pause'}, **headers).code, 403)

    def test_user_controls_require_origin_and_json_header(self):
        self.assertEqual(self.call({'action': 'pause'}).code, 403)
        self.assertEqual(self.call({'action': 'pause'}, Origin='http://127.0.0.1:8712').value['paused'], True)
        self.assertEqual(self.call({'action': 'pause'}, **{'Origin': 'http://127.0.0.1:8712', 'X-CFD-Activity': ''}).code, 403)

    def test_local_progress_accepted_without_exposing_controls(self):
        result = self.call({'action': 'start', 'name': 'Agent', 'mode': 'development', 'stage': 'debug', 'detail': 'Review'})
        self.assertEqual(result.code, 200)
        self.assertFalse(result.value['displayed'])
        self.assertEqual(self.call({'action': 'queue.start'}).code, 409)
        self.assertEqual(self.call().code, 200)


class ClientTests(unittest.TestCase):
    @patch('cfd_studio.agent_progress.urlopen')
    def test_old_server_unknown_route_is_not_success(self, opener):
        opener.side_effect = HTTPError('http://127.0.0.1', 404, 'missing', {}, io.BytesIO(b'{"err":"unknown"}'))
        self.assertEqual(request(8712), {'error': 'ACTIVITY_UNAVAILABLE', 'http_status': 404})

    @patch('cfd_studio.agent_progress.configured_port', return_value=8712)
    @patch('cfd_studio.agent_progress.request')
    def test_visible_receipt_for_a_newer_revision_does_not_confirm_request(self, request, port):
        request.side_effect = [
            {'server': 'server', 'revision': 1, 'task': {'id': 'task'}, 'displayed': False},
            {'server': 'server', 'revision': 2, 'task': {'id': 'task'}, 'displayed': True},
        ]
        with patch('sys.stdout', new_callable=io.StringIO) as stdout, patch('cfd_studio.agent_progress.time.sleep'):
            self.assertEqual(main(['status', '--wait-visible']), 2)
            self.assertIn('ACTIVITY_STALE', stdout.getvalue())

    @patch('cfd_studio.agent_progress.configured_port', return_value=8712)
    @patch('cfd_studio.agent_progress.request')
    def test_secret_saved_only_to_exclusive_session_file(self, request, port):
        request.return_value = {'token': 'private', 'revision': 1, 'task': {'id': 'task'}, 'displayed': False}
        with tempfile.TemporaryDirectory() as directory, patch('sys.stdout', new_callable=io.StringIO) as stdout:
            path = Path(directory) / 'session.json'
            args = ['start', '--session-file', str(path), '--stage', 'debug', '--detail', 'Review']
            self.assertEqual(main(args), 0)
            self.assertNotIn('private', stdout.getvalue())
            self.assertEqual(json.loads(path.read_text())['token'], 'private')
            self.assertEqual(main(args), 2)
            self.assertEqual(request.call_count, 1)

    @patch('cfd_studio.agent_progress.configured_port', return_value=8712)
    @patch('cfd_studio.agent_progress.request', return_value={'error': 'PAUSED'})
    def test_pause_is_nonzero_and_rejected_claim_leaves_no_file(self, request, port):
        with tempfile.TemporaryDirectory() as directory, patch('sys.stdout', new_callable=io.StringIO):
            path = Path(directory) / 'session.json'
            self.assertEqual(main(['start', '--session-file', str(path), '--stage', 'debug', '--detail', 'Review']), 3)
            self.assertFalse(path.exists())
