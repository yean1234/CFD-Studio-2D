import csv
import io
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from cfd_studio.csv_export import build_csv_archive, CSVExports, inventory
from cfd_studio.result_series import ResultSeries


class CSVExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'case';self.root.mkdir();self.target=Path(self.tmp.name)/'export.zip'
        self.record={'kind':'legacy','rid':'1','name':'=unsafe','path':str(self.root)}
        self.w=SimpleNamespace(output=self.root,discover=lambda:{'case:a':self.record})
        self.series=ResultSeries(self.w)
        (self.root/'case_config.json').write_text('{}')
    def packed(self,name,magic,values,channels=1):
        n=len(values)//channels
        (self.root/name).write_bytes(magic+struct.pack('<3I6f',n,1,1,0,0,0,2,1,1)+struct.pack('<'+str(len(values))+'f',*values))
    def rows(self,z,name):
        return list(csv.DictReader(io.StringIO(z.read(name).decode('utf-8-sig'))))
    def test_all_history_times_and_fields_export_without_changing_sources(self):
        self.packed('therm_0.bin',b'THM1',[0,300]);self.packed('therm_2.bin',b'THM1',[280,310])
        self.packed('flow_2.bin',b'FLW1',[3,4,0,0,0,12],3)
        (self.root/'history.json').write_text(json.dumps({'vapor':[[i,.123456789+i] for i in range(701)]}))
        before={p.name:p.read_bytes() for p in self.root.iterdir()}
        build_csv_archive(self.series,'case:a',self.target)
        with ZipFile(self.target) as z:
            rows=self.rows(z,'time_series.csv');volume=[r for r in rows if r['metric']=='volume']
            self.assertEqual(len(volume),701);self.assertEqual(float(volume[-1]['value']),700.123456789)
            self.assertTrue(any(r['metric']=='temperature.mean' for r in rows));self.assertTrue(any(r['metric']=='uz.max' for r in rows))
            raw=self.rows(z,'fields/therm_0.csv');self.assertEqual(len(raw),2)
            self.assertEqual(float(raw[0]['temperature_K']),0);self.assertEqual(float(raw[1]['x_m']),1.5)
            flow=self.rows(z,'fields/flow_2.csv');self.assertEqual(float(flow[1]['uz_m_s']),12)
            self.assertEqual(json.loads(z.read('manifest.json'))['spatial_representation'],'saved_visualization_grid')
        self.assertEqual({p.name:p.read_bytes() for p in self.root.iterdir()},before)
    def test_phase_mask_and_normalized_units_are_preserved(self):
        (self.root/'phase_1.bin').write_bytes(b'PHS2'+struct.pack('<3I6f',2,1,1,0,0,0,2,1,1)+bytes([51,255,102,0,1,0]))
        self.packed('concentration_1.bin',b'CON1',[.25,.75])
        build_csv_archive(self.series,'case:a',self.target)
        with ZipFile(self.target) as z:
            phase=self.rows(z,'fields/phase_1.csv');self.assertEqual(phase[1]['valid_mask'],'0');self.assertAlmostEqual(float(phase[0]['liquid_fraction']),.4)
            self.assertEqual(float(self.rows(z,'fields/concentration_1.csv')[0]['concentration_C_over_Cref']),.25)
    def test_corrupt_source_never_becomes_downloadable_and_temporary_file_is_removed(self):
        self.packed('therm_1.bin',b'THM1',[float('nan')]);export=CSVExports(self.series)
        folder=Path(self.tmp.name)/'temporary';folder.mkdir()
        with patch('cfd_studio.csv_export.tempfile.mkdtemp',return_value=str(folder)):
            with self.assertRaises(ValueError):export.prepare('case:a')
        self.assertFalse(folder.exists());self.assertEqual(export.files,{});self.assertEqual(export.busy,set())
    def test_changed_inventory_is_rejected(self):
        self.packed('therm_1.bin',b'THM1',[300]);before=inventory(self.root)
        with patch('cfd_studio.csv_export.inventory',side_effect=[before,{}]):
            with self.assertRaisesRegex(ValueError,'결과가 변경'):build_csv_archive(self.series,'case:a',self.target)
    def test_download_is_streamed_once_and_temporary_copy_is_removed(self):
        self.packed('therm_1.bin',b'THM1',[300]);export=CSVExports(self.series);result=export.prepare('case:a')
        path=export.files[result['token']][0]
        handler=SimpleNamespace(wfile=io.BytesIO(),send_response=lambda s:None,send_header=lambda *a:None,end_headers=lambda:None)
        export.download(handler,result['token'])
        with ZipFile(io.BytesIO(handler.wfile.getvalue())) as z:self.assertIn('time_series.csv',z.namelist())
        self.assertFalse(path.parent.exists())
        with self.assertRaises(ValueError):export.download(handler,result['token'])
    def test_warehouse_export_has_every_cell_and_raw_value(self):
        from tests.test_warehouse_results import WarehouseResultTests
        fixture=WarehouseResultTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.record.update(kind='warehouse',rid=fixture.case.name,path=str(fixture.case))
        build_csv_archive(self.series,'case:a',self.target)
        with ZipFile(self.target) as z:
            rows=self.rows(z,'fields/frame_000001.csv')
            self.assertEqual(len(rows),2);self.assertEqual(float(rows[1]['concentration_C/C_ref']),3)
            self.assertEqual(float(rows[1]['x_m']),1.5)
            self.assertEqual(json.loads(z.read('manifest.json'))['spatial_representation'],'saved_solver_cells')

if __name__=='__main__':unittest.main()
