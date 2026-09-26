import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
import zipfile
from study_platform.contracts import candidates
from study_platform.service import Service, Conflict
from study_platform.packages import inspect, import_package

DESIGN = {'variable': 'K_porous_m2_s', 'method': 'manual', 'values': [.001, .002, .004], 'seed': 42}


class StudyTests(unittest.TestCase):
    def make(self, root, adapter=None):
        store = Service(root, adapter=adapter)
        study = store.create('benchmark')
        preview = candidates(DESIGN)
        revision = store.commit(study, DESIGN, preview['preview_hash'], None)
        return store, study, revision

    def test_sampling_reproducible_baseline_and_exclusions(self):
        preview = candidates(DESIGN)
        self.assertEqual(sum(row['valid'] for row in preview['candidates']), 3)
        self.assertTrue(preview['candidates'][0]['baseline'])
        design = {'variable': 'porosity', 'method': 'latin_hypercube_1d', 'low': .2, 'high': .6, 'count': 6, 'seed': 50}
        self.assertEqual(candidates(design), candidates(design))
        self.assertNotEqual(candidates(design), candidates({**design, 'seed': 51}))
        for value in (float('nan'), float('inf'), True):
            with self.assertRaises(ValueError):
                candidates({**DESIGN, 'values': [value]})

    def test_hash_conflict_immutability_and_idempotency(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, study, rev = self.make(tmp)
            with self.assertRaises(Conflict):
                store.commit(study, DESIGN, candidates(DESIGN)['preview_hash'], None)
            with store.db() as db, self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE cases SET input='{}'")
            first = store.enqueue(rev['cases'], 'request-one')
            self.assertEqual(first, store.enqueue(rev['cases'], 'request-one'))
            with self.assertRaises(Conflict):
                store.enqueue(rev['cases'], 'request-two')
            with self.assertRaises(Conflict):
                store.enqueue([rev['cases'][0]], 'request-one')

    def test_sequential_owner_and_quality_gate(self):
        calls = []; active = []
        def fake(folder, spec, code, resume):
            self.assertFalse(active)
            active.append(1); calls.append(folder)
            time.sleep(.02); active.pop()
            return {'pass': len(calls) != 2}
        with tempfile.TemporaryDirectory() as tmp:
            store, study, rev = self.make(tmp, fake)
            store.enqueue(rev['cases'], 'request')
            threads = [threading.Thread(target=store.drain) for _ in range(3)]
            for t in threads: t.start()
            for t in threads: t.join()
            attempts = store.detail(study)['attempts']
            self.assertEqual(len(calls), 3)
            self.assertEqual(len(set(calls)), 3)
            self.assertEqual([a['state'] for a in attempts], ['finished']*3)
            self.assertEqual([a['quality'] for a in attempts], ['pass', 'fail', 'pass'])
            self.assertEqual(len(store.comparison(study)['excluded']), 3)  # mock has no physical metrics

    def test_pause_cancel_and_orphan_not_restarted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, study, rev = self.make(tmp, lambda *args: {'pass': True})
            ids = store.enqueue(rev['cases'], 'request')['attempts']
            store.pause(True); store.drain()
            self.assertTrue(all(a['state'] == 'queued' for a in store.detail(study)['attempts']))
            store.cancel_queued(ids[0])
            with store.db() as db:
                db.execute("UPDATE attempts SET state='running',owner='lost' WHERE id=?", (ids[1],))
            store.pause(False); store.drain()
            states = [a['state'] for a in store.detail(study)['attempts']]
            self.assertEqual(states, ['cancelled', 'recovery_required', 'queued'])

    def test_modified_code_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, study, rev = self.make(tmp, lambda *args: self.fail('must not execute'))
            code = Path(tmp)/'revisions'/rev['revision']/'code/tracer_transport/run.py'
            code.write_text('changed')
            store.enqueue(rev['cases'], 'request'); store.drain()
            self.assertTrue(all(a['state'] == 'failed' for a in store.detail(study)['attempts']))

    def test_unicode_project_metadata_is_preserved(self):
        def fake(folder, *args):
            viewer = folder/'viewer'; viewer.mkdir()
            (viewer/'meta.json').write_text(json.dumps({'run_id': 'tracer-test', 'description': '농도 검증'}, ensure_ascii=False), encoding='utf-8')
            return {'pass': True}
        with tempfile.TemporaryDirectory() as tmp:
            store, study, rev = self.make(Path(tmp)/'study', fake)
            store.project_root = Path(tmp)/'projects'
            store.enqueue([rev['cases'][0]], 'unicode'); store.drain()
            attempt = store.detail(study)['attempts'][0]
            self.assertEqual(attempt['quality'], 'pass')
            metadata = json.loads((store.project_root/attempt['result']['project_folder']/'meta.json').read_text(encoding='utf-8'))
            self.assertEqual(metadata['description'], '농도 검증')

    def test_candidate_failure_and_retry_preserve_attempt(self):
        calls = []
        def fake(folder, *args):
            calls.append(folder)
            if len(calls) == 1:
                raise ValueError('candidate test failure')
            return {'pass': True}
        with tempfile.TemporaryDirectory() as tmp:
            store, study, rev = self.make(tmp, fake)
            store.enqueue(rev['cases'], 'first'); store.drain()
            original = store.detail(study)['attempts']
            self.assertEqual([a['state'] for a in original], ['failed', 'finished', 'finished'])
            store.enqueue([rev['cases'][0]], 'retry'); store.drain()
            attempts = store.detail(study)['attempts']
            self.assertEqual(len(attempts), 4)
            self.assertEqual(attempts[0], original[0])
            self.assertEqual(attempts[-1]['quality'], 'pass')

    def test_environment_failure_pauses_queue(self):
        def bad(*args):
            raise OSError('missing solver')
        with tempfile.TemporaryDirectory() as tmp:
            store, study, rev = self.make(tmp, bad)
            store.enqueue(rev['cases'], 'first'); store.drain()
            data = store.detail(study)
            self.assertTrue(data['paused'])
            self.assertEqual([a['state'] for a in data['attempts']], ['failed', 'queued', 'queued'])

    def test_preview_hash_and_field_provider(self):
        import numpy as np
        from study_platform.fields import FieldProvider
        with tempfile.TemporaryDirectory() as tmp:
            store = Service(tmp)
            study = store.create('hash')
            with self.assertRaises(Conflict):
                store.commit(study, DESIGN, 'not-reviewed', None)
            file = Path(tmp)/'field.npz'
            np.savez(file, times=[0, 1], concentration=[[1, 2], [2, 3]], region_id=[0, 1], shape_xyz=[2, 1, 1], lengths_m=[2, 1, 1])
            provider = FieldProvider(file)
            self.assertEqual(provider.query([.2, .2, .2], .5)['value'], 1.5)
            self.assertFalse(provider.query([.2, .2, .2], .5, 'temperature')['valid'])
            self.assertFalse(provider.query([.2, .2, .2], .5, region_id=1)['valid'])
            self.assertFalse(provider.query([.2, .2, .2], 5)['valid'])

    def test_archive_paths_and_hashes(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('../escape', '/absolute', 'C:/escape', 'x\\y', 'AUX.txt', 'dir./x', 'x '):
                file = root/'bad.zip'
                with zipfile.ZipFile(file, 'w') as archive:
                    archive.writestr(name, b'data'); archive.writestr('manifest.json', '{}')
                with self.assertRaises(ValueError): inspect(file)
            good = root/'good.zip'
            manifest = {'schema_version': 1, 'level': 'A', 'files': {'data.txt': {'size': 4, 'sha256': hashlib.sha256(b'data').hexdigest()}}}
            with zipfile.ZipFile(good, 'w') as archive:
                archive.writestr('data.txt', b'data'); archive.writestr('manifest.json', json.dumps(manifest))
            import_package(good, root/'imported')
            self.assertEqual((root/'imported/data.txt').read_bytes(), b'data')
            with self.assertRaises(FileExistsError): import_package(good, root/'imported')
            with zipfile.ZipFile(root/'tampered.zip', 'w') as archive:
                archive.writestr('data.txt', b'evil'); archive.writestr('manifest.json', json.dumps(manifest))
            with self.assertRaises(ValueError): inspect(root/'tampered.zip')


if __name__ == '__main__':
    unittest.main()
