import copy
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from cfd_studio.execution_workspace import ExecutionWorkspace, get_route, post_route
from cfd_studio.solver_catalog import CATALOG, catalog, draft_config, probe

ROOT=Path(__file__).resolve().parents[1]


class SolverCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)
        self.w=ExecutionWorkspace(ROOT,[],folder=self.folder/'registry',output=self.folder/'output')

    def test_catalog_has_ten_general_and_two_dedicated_solvers(self):
        items=catalog()
        self.assertEqual(sum(not x['dedicated'] for x in items),10)
        self.assertEqual(len({x['id'] for x in items}),12)
        for item in items:
            self.assertTrue(item['summary'] and item['inputs'] and item['outputs'])
            self.assertEqual(item['installation'],'unchecked')
        items[0]['outputs'].clear()
        self.assertTrue(catalog()[0]['outputs'])

    def test_installation_does_not_enable_an_unconnected_adapter(self):
        stdout='VERSION\t2312\n'+''.join(x['id']+'\tfound\n' for x in CATALOG)
        with patch('cfd_studio.solver_catalog.subprocess.run',return_value=Mock(returncode=0,stdout=stdout.encode('utf-8'))) as run:
            result=probe({})
        self.assertEqual(result['status'],'checked')
        item=next(x for x in catalog(result) if x['id']=='interFoam')
        self.assertEqual(item['installation'],'found')
        self.assertEqual(item['integration'],'definition_only')
        script=run.call_args.kwargs['input']
        self.assertIsInstance(script,bytes)
        self.assertNotIn(b'\r',script)
        self.assertNotIn('text',run.call_args.kwargs)
        self.assertIn(b'type -P interFoam',script)
        self.assertNotIn(b'interFoam -',script)

    def test_probe_failure_is_unknown_not_missing(self):
        for failure in (OSError('missing bash'),subprocess.TimeoutExpired('bash',15)):
            with patch('cfd_studio.solver_catalog.subprocess.run',side_effect=failure):
                result=probe({})
            self.assertEqual(result['status'],'unavailable')
            self.assertTrue(all(x['installation']=='unchecked' for x in catalog(result)))

    def test_draft_survives_restart_but_cannot_create_project_or_preset(self):
        config=draft_config('chtMultiRegionFoam');config['requirements']['geometry']='고체·유체 영역 구분'
        saved=self.w.save_form('복합 열전달','solver_definition','chtMultiRegionFoam',config)
        fresh=ExecutionWorkspace(ROOT,[],folder=self.folder/'registry',output=self.folder/'output')
        form=fresh.form(saved['id'])
        self.assertTrue(form['definition_only']);self.assertEqual(form['config'],config)
        self.assertFalse(any(p['form_id']==form['id'] for p in fresh.presets()))
        with self.assertRaisesRegex(ValueError,'초안'):
            fresh.create_project('오류',form_id=form['id'],storage_path=str(self.folder/'project'))
        self.assertFalse((self.folder/'project').exists())
        with self.assertRaisesRegex(ValueError,'초안'):
            fresh.save_scoped_preset('오류',config,form['id'])

    def test_cannot_smuggle_an_existing_config_into_an_unconnected_solver(self):
        original=self.w.form('immersion')
        with self.assertRaises(ValueError):
            self.w.save_form('잘못된 연결','immersion','interFoam',original['config'])
        with self.assertRaises(ValueError):
            self.w.save_form('잘못된 초안','solver_definition','interFoam',original['config'])
        bad=draft_config('icoFoam');bad['solver']='interFoam'
        with self.assertRaises(ValueError):self.w.save_form('불일치','solver_definition','icoFoam',bad)

    def test_connected_silo_solver_still_uses_existing_execution_config(self):
        c=copy.deepcopy(self.w.form('grain_silo')['config'])
        c['openfoam_mapping']['solver']='pimpleFoam'
        c['openfoam_mapping']['pressure_velocity_coupling']='PIMPLE'
        c['run']['time_basis']='physical_time'
        form=self.w.save_form('비정상 사일로','grain_silo','pimpleFoam',c)
        self.assertFalse(self.w.form(form['id'])['definition_only'])
        self.w.check_form_config(form['id'],c)

    def test_catalog_polling_never_launches_environment_checks(self):
        with patch('cfd_studio.solver_catalog.probe',return_value={'solvers':{}}) as check:
            h=Mock(path='/api/executions/solvers');get_route(h,self.w)
            self.assertEqual(len(h._json.call_args.args[0]['solvers']),12)
            check.assert_not_called()
            h=Mock(path='/api/executions/solver-check');post_route(h,self.w,{})
            check.assert_called_once()


if __name__=='__main__':unittest.main()

class ResultAxisTests(unittest.TestCase):
    def test_axes_follow_registered_solver_or_custom_snapshot(self):
        from cfd_studio.solver_catalog import result_axis
        self.assertEqual(result_axis({'analysis': {'solver': 'buoyantSimpleFoam'}}), 'iteration')
        self.assertEqual(result_axis({'analysis': {'solver': 'buoyantPimpleFoam'}, 'run': {'time_basis': 'iterations'}}), 'time')
        self.assertEqual(result_axis({'analysis': {'solver': 'custom'}, 'run': {'time_basis': 'iterations'}}), 'iteration')
        self.assertEqual(result_axis({'run': {'time_basis': 'physical_time'}}), 'time')
