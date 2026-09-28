import json
import math
from pathlib import Path
import struct
import tempfile
import unittest
from cfd_studio.result_series import ResultSeries, output_definitions


class Workspace:
    def __init__(self, root): self.output=root
    def discover(self): return {'case:a':{'path':str(self.output),'kind':'legacy','rid':'a','name':'A'}}


class SeriesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.series=ResultSeries(Workspace(self.root))
        (self.root/'case_config.json').write_text(json.dumps({'tank':{},'dielectric_fluid':{}}))
    def packed(self,name,magic,values,channels=1):
        n=len(values)//channels;data=magic+struct.pack('<3I6f',n,1,1,0,0,0,1,1,1)+struct.pack('<'+str(len(values))+'f',*values)
        path=self.root/name;path.write_bytes(data);return path
    def test_time_order_pagination_temperature_units_and_no_result_mutation(self):
        a=self.packed('therm_10.bin',b'THM1',[0,300,310]);b=self.packed('therm_2.bin',b'THM1',[280,290,0]);before=[a.read_bytes(),b.read_bytes()]
        first=self.series.page('case:a','temperature.mean',0,1);second=self.series.page('case:a','temperature.mean',first['next'],1)
        self.assertEqual(first['axis'],'time');self.assertEqual(first['total'],2);self.assertEqual(first['points'][0][0],2)
        self.assertAlmostEqual(first['points'][0][1],11.85);self.assertAlmostEqual(second['points'][0][1],31.85)
        self.assertEqual([a.read_bytes(),b.read_bytes()],before)
    def test_vector_components_and_pressure_conversion_keep_steady_axis(self):
        (self.root/'case_config.json').write_text(json.dumps({'openfoam_mapping':{'solver':'simpleFoam'},'published':{'rho_kg_m3':2}}))
        self.packed('flow_100.bin',b'FLW1',[3,4,0,0,0,12],3);self.packed('pressure_100.bin',b'PRS1',[2,4])
        self.assertEqual(self.series.page('case:a','speed.mean')['points'],[[100,8.5]])
        self.assertEqual(self.series.page('case:a','ux.max')['points'],[[100,3]])
        self.assertEqual(self.series.page('case:a','pressure.mean')['points'],[[100,6]])
        c=self.series.catalog('case:a');self.assertEqual(c['axis'],'iteration');self.assertEqual(next(m['unit'] for m in c['metrics'] if m['id']=='pressure.mean'),'Pa')
    def test_corrupt_frame_is_a_gap_and_retry_uses_changed_file(self):
        path=self.packed('therm_1.bin',b'THM1',[300,float('nan')]);r=self.series.page('case:a','temperature.max');self.assertIsNone(r['points'][0][1]);self.assertTrue(r['errors'])
        self.packed('therm_1.bin',b'THM1',[310,320]);r=self.series.page('case:a','temperature.max');self.assertFalse(r['errors']);self.assertAlmostEqual(r['points'][0][1],46.85)
    def test_phase_mask_and_turbulence_channel_semantics(self):
        header=b'PHS2'+struct.pack('<3I6f',2,1,1,0,0,0,1,1,1)
        (self.root/'phase_1.bin').write_bytes(header+bytes([51,255,102,255,1,0]))
        self.assertAlmostEqual(self.series.page('case:a','liquid.mean')['points'][0][1],.4)
        self.packed('turbulence_1.bin',b'TRB1',[1,3,10,20],2)
        self.assertEqual(self.series.page('case:a','k.mean')['points'],[[1,2]])
        self.assertEqual(self.series.page('case:a','epsilon.max')['points'],[[1,20]])
    def test_saved_history_retains_all_points_and_precision(self):
        rows=[[float(i)/10,.123456789+i] for i in range(700)]
        (self.root/'history.json').write_text(json.dumps({'vapor':rows}))
        actual=[]
        for offset in range(0,700,32): actual.extend(self.series.page('case:a','volume',offset,32)['points'])
        self.assertEqual([list(r) for r in actual],rows)
        with self.assertRaises(ValueError):self.series.page('case:a','volume',0,100000)
        with self.assertRaises(ValueError):self.series.page('case:a','unknown')
    def test_form_outputs_describe_computed_channels_without_fabricating_missing_results(self):
        self.assertIn('epsilon',{d['id'] for d in output_definitions('grain_silo')})
        self.assertIn('probe1',{d['id'] for d in output_definitions('immersion')})
        self.assertEqual(self.series.catalog('case:a')['metrics'],[])

    def test_layer_statistics_use_saved_interface_height(self):
        (self.root/'case_config.json').write_text(json.dumps({'layers':{'dielectric_mm':500}}))
        raw=b'THM1'+struct.pack('<3I6f',1,2,1,0,0,0,1,1,1)+struct.pack('<2f',290,310)
        (self.root/'therm_1.bin').write_bytes(raw)
        self.assertAlmostEqual(self.series.page('case:a','lower_temperature.mean')['points'][0][1],16.85)
        self.assertAlmostEqual(self.series.page('case:a','upper_temperature.mean')['points'][0][1],36.85)
    def test_coil_inputs_and_derived_outlet_use_case_snapshot(self):
        coil={'Ta_C':20,'flow_LPM':60,'h_W_m2K':4178/6,'x0':0,'x1':1000,'y0':0,'y1':1000,'z0':0,'z1':1000}
        (self.root/'case_config.json').write_text(json.dumps({'coil':coil}))
        (self.root/'history.json').write_text(json.dumps({'coil':[[0,30],[1,40]]}))
        self.assertEqual(self.series.page('case:a','t5')['points'],[(0,20),(1,20)])
        self.assertEqual(self.series.page('case:a','t6')['points'],[(0,30),(1,40)])
        coil['flow_LPM']=0
        (self.root/'case_config.json').write_text(json.dumps({'coil':coil}))
        self.assertNotIn('t6',{m['id'] for m in self.series.catalog('case:a')['metrics']})
