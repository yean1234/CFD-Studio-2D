"""Component mesh controls must not become materials, walls or cell zones."""
import copy
import unittest
from tmc49_full_tank.tools.mesh_refinement import collect_refinements, refinement_boxes, validate_overlap, requested_spacing
from tmc49_full_tank.tools.build_case import build_mesh
from tests.test_local_refinement import mesh_config
from cfd_studio.form_schema import validate_geometry, blank_schema, config_from_schema, apply_initial_geometry


def helper(lo=(10,10,10),hi=(30,30,30),size=2):
    return {'name':'Inspection','material_state':'mesh_refinement','shape':'box','unit':'mm','min':list(lo),'max':list(hi),'mesh_control':{'cell_size':{'value':size,'unit':'mm'}}}


class MeshComponentTests(unittest.TestCase):
    def test_containment_order_duplicate_units_and_touching(self):
        outer=([0,0,0],[100,100,100],5);inner=([10,10,10],[90,90,90],2)
        for boxes in [[outer,inner],[inner,outer]]:
            self.assertEqual(requested_spacing([50]*3,validate_overlap(boxes),10),2)
            self.assertEqual(requested_spacing([5]*3,boxes,10),5)
        self.assertEqual(len(validate_overlap([outer,outer])),1)
        validate_overlap([outer,([100,0,0],[120,100,100],2)])
        c=mesh_config();c['tank']['mesh_control']={'cell_size':{'value':.005,'unit':'m'}}
        c['mesh_regions']=[helper(size=2)];c['mesh']['refinement_regions']=[{'shape':'box','unit':'m','min':[0,0,0],'max':[.1,.1,.1],'cell_size':{'value':5,'unit':'mm'}}]
        self.assertEqual(len(refinement_boxes(c['mesh'],[100]*3,c)),2)

    def test_ambiguous_and_unsupported_overlaps_fail_before_generation(self):
        outer=([0,0,0],[100,100,100],5)
        for box in [([0,0,0],[100,100,100],2),([50,50,50],[150,150,150],2)]:
            with self.assertRaisesRegex(ValueError,'MESH-R006'):validate_overlap([outer,box])
        inner=([10,10,10],[90,90,90],7)
        self.assertEqual(requested_spacing([50]*3,[outer,inner],10),7)
        with self.assertRaisesRegex(ValueError,'MESH-R007'):validate_overlap([outer,inner])
        c=mesh_config();c['tank']['mesh_control']={'cell_size':{'value':5,'unit':'mm'}};c['mesh_regions']=[helper(size=7)]
        with self.assertRaisesRegex(ValueError,'MESH-R007'):build_mesh(c)

    def test_mesh_only_refines_without_adding_boundary_or_changing_geometry(self):
        c=mesh_config();base=build_mesh(c);before=copy.deepcopy(c)
        c['mesh_regions']=[helper()];refined=build_mesh(c)
        self.assertGreater(refined[1],base[1]);self.assertEqual(refined[2:4],base[2:4])
        self.assertNotIn('Inspection',refined[0]);self.assertEqual(c['tank'],before['tank']);validate_geometry(c)
        for key,value in [('properties',{}),('fill',{}),('boundary_conditions',{}),('role','wall')]:
            bad=copy.deepcopy(c);bad['mesh_regions'][0][key]=value
            with self.assertRaisesRegex(ValueError,'MESH-R008'):collect_refinements(bad)
        bad=copy.deepcopy(c);bad['mesh_regions']=[None]
        with self.assertRaisesRegex(ValueError,'MESH-R008'):collect_refinements(bad)
        c['regions']=c.pop('mesh_regions')
        with self.assertRaisesRegex(ValueError,'MESH-R008'):collect_refinements(c)

    def test_warehouse_mesh_only_preserves_volume_and_loaded_grain(self):
        import numpy as np
        from tracer_transport.porous_warehouse_mesh import generate_mesh
        c={'geometry_spec':{'geometry':{'length_m':6,'width_m':4,'eaves_m':3,'roof_rise_m':1}},'loading':{'blocks':[{'min_m':[1,1,.5],'max_m':[2,3,2]}]},'porous_mesh':{'kind':'aligned_grain_blocks','base_max_spacing_m':[1,1,1],'refinement':1,'maximum_cells':100000}}
        _,base=generate_mesh(c);c['mesh_regions']=[helper((100,100,100),(500,500,500),250)]
        _,fine=generate_mesh(c)
        self.assertGreater(len(fine['cell_volumes_m3']),len(base['cell_volumes_m3']))
        self.assertAlmostEqual(float(np.sum(fine['cell_volumes_m3'])),float(np.sum(base['cell_volumes_m3'])))
        self.assertAlmostEqual(float(np.sum(fine['cell_volumes_m3']*fine['loaded_region'])),float(np.sum(base['cell_volumes_m3']*base['loaded_region'])))

    def test_silo_mesh_only_controls_are_connected(self):
        from tests.test_silo_contract import draft,normalizer
        from tmc49_full_tank.tools.build_silo_runtime import block_mesh
        c=draft();c['mesh']['target_cells']=4000;base=block_mesh(c)[1]
        c['mesh_regions']=[helper((-100,-100,400),(100,100,600),30)]
        ok,c,message=normalizer()(c);self.assertTrue(ok,message);text,plan=block_mesh(c)
        self.assertGreater(plan['actual_cells'],base['actual_cells']);self.assertNotIn('Inspection',text)

    def test_folders_and_mesh_controls_survive_template_blank(self):
        c={'geometry':{'regions':[{'name':'Box','shape':'box','unit':'m','min':[0,0,0],'max':[1,1,1],'editor_group':'folder-a','mesh_control':{'cell_size':{'value':.05,'unit':'m'}}}]},'_studio':{'geometry_groups':[{'id':'folder-a','name':'Parts','expanded':False}]},'mesh':{'cell_size':{'value':.1,'unit':'m'}}}
        schema=blank_schema(c);blank=config_from_schema(schema)
        self.assertEqual(blank['geometry'],c['geometry']);self.assertEqual(blank['_studio']['geometry_groups'],c['_studio']['geometry_groups']);validate_geometry(blank)
        applied=apply_initial_geometry({'geometry':{'regions':[]}},schema)
        self.assertEqual(applied['_studio']['geometry_groups'],c['_studio']['geometry_groups']);validate_geometry(applied)
        c['_studio']['geometry_groups']=[]
        with self.assertRaisesRegex(ValueError,'MESH-R009'):validate_geometry(c)


if __name__=='__main__':unittest.main()
