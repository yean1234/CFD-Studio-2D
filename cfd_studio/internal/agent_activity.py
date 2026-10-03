"""Publish agent progress and cooperative pause signals, never CFD commands."""
from collections import deque
import copy
import json
import secrets
import threading
import time
from urllib.parse import urlparse

STAGES = {'review', 'draft', 'debug', 'test', 'ui', 'waiting', 'blocked', 'completed', 'failed'}
TERMINAL = {'completed', 'failed'}


class ActivityError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class Activity:
    """One process-local owner; pause survives expiry and new claim attempts."""
    def __init__(self, clock=time.monotonic, wall=time.time, ttl=120):
        self.clock, self.wall, self.ttl = clock, wall, ttl
        self.lock = threading.RLock()
        self.server = secrets.token_hex(12)
        self.token = None
        self.task = None
        self.paused = False
        self.revision = 0
        self.deadline = 0
        self.history = deque(maxlen=20)
        self.viewers = {}

    def _snapshot(self):
        task = copy.deepcopy(self.task)
        if task:
            task['connected'] = self.clock() < self.deadline
            task['status'] = ('paused' if self.paused else task['stage'] if
                              task['stage'] in TERMINAL or task['connected'] else 'disconnected')
        # A receipt proves only that a visible Studio tab rendered this revision
        visible = any(seen['revision'] == self.revision and self.clock() - seen['at'] < 8
                      for seen in self.viewers.values())
        return {'server': self.server, 'revision': self.revision, 'task': task, 'paused': self.paused,
                'displayed': visible, 'history': copy.deepcopy(list(self.history))}

    def snapshot(self):
        with self.lock:
            return self._snapshot()

    def _text(self, value, limit):
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ActivityError('ACTIVITY_INVALID_INPUT')
        return value.strip()

    def dispatch(self, body):
        if not isinstance(body, dict):
            raise ActivityError('ACTIVITY_INVALID_INPUT')
        with self.lock:
            action = body.get('action')
            if action == 'seen':
                tab = self._text(body.get('tab'), 80)
                revision = body.get('revision')
                if type(revision) is not int or revision != self.revision:
                    raise ActivityError('ACTIVITY_STALE')
                self.viewers = {key: value for key, value in self.viewers.items()
                                if self.clock() - value['at'] < 8}
                if len(self.viewers) >= 16 and tab not in self.viewers:
                    raise ActivityError('ACTIVITY_BUSY')
                self.viewers[tab] = {'revision': revision, 'at': self.clock()}
                return self._snapshot()
            if action in ('pause', 'resume'):
                self.paused = action == 'pause'
                self.revision += 1
                return self._snapshot()
            if action == 'start':
                if self.paused:
                    raise ActivityError('PAUSED')
                if self.task and self.task['stage'] not in TERMINAL and self.clock() < self.deadline:
                    raise ActivityError('ACTIVITY_BUSY')
                name = self._text(body.get('name'), 80)
                detail = self._text(body.get('detail'), 240)
                stage = body.get('stage')
                mode = body.get('mode')
                if not isinstance(stage, str) or stage not in STAGES - TERMINAL or mode not in ('development', 'operation'):
                    raise ActivityError('ACTIVITY_INVALID_INPUT')
                self.token = secrets.token_urlsafe(32)
                self.task = {'id': secrets.token_hex(12), 'name': name, 'mode': mode,
                             'stage': stage, 'detail': detail}
                self.history.clear()
            elif action in ('update', 'finish'):
                if not isinstance(body.get('token'), str) or not self.token or not secrets.compare_digest(body['token'], self.token):
                    raise ActivityError('ACTIVITY_OWNER_MISMATCH')
                if self.task['stage'] in TERMINAL:
                    raise ActivityError('ACTIVITY_FINISHED')
                if self.paused and action != 'finish':
                    raise ActivityError('PAUSED')
                stage = body.get('stage')
                if not isinstance(stage, str) or stage not in (TERMINAL if action == 'finish' else STAGES - TERMINAL):
                    raise ActivityError('ACTIVITY_INVALID_INPUT')
                detail = self._text(body.get('detail'), 240)
                self.task.update(stage=stage, detail=detail)
            else:
                raise ActivityError('ACTIVITY_UNKNOWN_ACTION')
            self.deadline = self.clock() + self.ttl
            self.task['updated_at'] = self.wall()
            self.revision += 1
            self.history.append({key: self.task[key] for key in ('stage', 'detail', 'updated_at')})
            result = self._snapshot()
            if action == 'start':
                result['token'] = self.token
            return result


ACTIVITY = Activity()


def route(handler, *, post=False, activity=ACTIVITY):
    """Same-origin, loopback-only status transport with no executable payloads."""
    if urlparse(handler.path).path != '/api/agent/activity':
        return False
    try:
        host = handler.headers.get('Host', '')
        parsed = urlparse('http://' + host)
        if handler.client_address[0] not in ('127.0.0.1', '::1') or parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise ActivityError('ACTIVITY_FORBIDDEN')
        origin = handler.headers.get('Origin')
        if origin and origin != 'http://' + host:
            raise ActivityError('ACTIVITY_FORBIDDEN')
        if handler.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise ActivityError('ACTIVITY_FORBIDDEN')
        if not post:
            handler._json(activity.snapshot())
            return True
        if handler.headers.get('X-CFD-Activity') != '1' or handler.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            raise ActivityError('ACTIVITY_FORBIDDEN')
        length = int(handler.headers.get('Content-Length', '0'))
        if not 0 < length <= 4096:
            raise ActivityError('ACTIVITY_INVALID_INPUT')
        body = json.loads(handler.rfile.read(length))
        # Only same-origin browser controls may issue user pause/resume receipts
        if isinstance(body, dict) and body.get('action') in ('pause', 'resume', 'seen') and not origin:
            raise ActivityError('ACTIVITY_FORBIDDEN')
        handler._json(activity.dispatch(body))
    except ActivityError as exc:
        handler._json({'error': exc.code, 'state': activity.snapshot()},
                      403 if exc.code == 'ACTIVITY_FORBIDDEN' else 409)
    except (ValueError, UnicodeError):
        handler._json({'error': 'ACTIVITY_INVALID_INPUT'}, 400)
    return True
