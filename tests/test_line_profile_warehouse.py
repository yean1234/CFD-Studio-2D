import unittest
from tests import test_warehouse_results as fixtures
from cfd_studio.result_series import ResultSeries

class LineProfileWarehouseTests(unittest.TestCase):
    setUp = fixtures.WarehouseResultTests.setUp
    def test_saved_profile_and_domain(self):
        case,root=self.case,self.root
        class Workspace:
            output=root
            def discover(self):return {'w':{'path':str(case),'kind':'warehouse','rid':case.name,'name':'Fixture'}}
        series=ResultSeries(Workspace())
        self.assertEqual(series.profile_frames('w','concentration')['times'],[0,1])
        r=series.line_profile('w','concentration',[.5,.5,.5],[1.5,1.5,.5],1,2)
        self.assertEqual([p[1] for p in r['points']],[2,3]);self.assertEqual(r['unit'],'C/C_ref')
        self.assertEqual([p['cell_index'] for p in r['samples']],[0,1])
        with self.assertRaises(ValueError):series.line_profile('w','concentration',[0,0,2.5],[1,1,1])
        (case/'1/C').write_text('internalField uniform 99; boundaryField {}')
        with self.assertRaisesRegex(ValueError,'일치하지'):series.line_profile('w','concentration',[.5,.5,.5],[1.5,1.5,.5],1,2)
