import copy
import unittest
from cfd_studio.primitive_geometry import validate_runner_geometry
from cfd_studio.form_schema import blank_schema,config_from_schema,validate_geometry
from cfd_studio.execution_workspace import validate_settings

class PrimitiveGeometryTests(unittest.TestCase):
    def test_box_compatibility_with_units_and_unchanged_source(self):
        c={'tank':{'shape':'box','unit':'m','min':[0,0,0],'max':[.456,.8,.07],
                   'width_mm':456,'depth_mm':70,'liquid_height_mm':800}}
        before=copy.deepcopy(c);validate_geometry(c);validate_runner_geometry(c);self.assertEqual(c,before)
        blank=config_from_schema(blank_schema(c));self.assertEqual(blank['tank']['shape'],'box');self.assertEqual(blank['tank']['max'],[.456,.8,.07])

    def test_old_runner_rejects_unsupported_or_mismatched_geometry(self):
        c={'tank':{'shape':'sphere','unit':'m','center':[0,0,0],'radius':2,'width_mm':456,'depth_mm':70,'liquid_height_mm':800}}
        validate_geometry(c)
        with self.assertRaisesRegex(ValueError,'직육면체'):validate_settings(c)
        c['tank'].update(shape='box',min=[0,0,0],max=[1,2,3])
        with self.assertRaisesRegex(ValueError,'치수'):validate_runner_geometry(c)
        c['tank']['min']=[True,0,0]
        with self.assertRaises(ValueError):validate_geometry(c)

    def test_generic_primitives_do_not_require_liquid_height(self):
        for part in [dict(shape='box',unit='m',min=[0,0,0],max=[1,2,3]),dict(shape='sphere',unit='mm',center=[0,0,0],radius=10),dict(shape='cylinder',unit='cm',center=[0,0,0],radius=2,height=3,axis='z')]:
            validate_geometry({'geometry':{'regions':[part]}})
            validate_runner_geometry({'geometry':{'regions':[part]}})

    def test_loading_explicit_box_cannot_disagree_with_runner_dimensions(self):
        p={'shape':'box','unit':'m','min':[0,0,0],'max':[1,2,3],'min_m':[0,0,0],'max_m':[1,2,3]}
        validate_runner_geometry({'loading':{'blocks':[p]}})
        p['max'][2]=4
        with self.assertRaises(ValueError):validate_runner_geometry({'loading':{'blocks':[p]}})
