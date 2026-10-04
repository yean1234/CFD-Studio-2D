import copy
import unittest
from tmc49_full_tank.tools.mesh_refinement import refinement_boxes,refined_axis
from tmc49_full_tank.tools.build_case import build_mesh
from cfd_studio.primitive_geometry import validate_fill_definitions


def mesh_config():
    return {'tank':{'width_mm':100,'liquid_height_mm':100,'depth_mm':100},'board':{'x0':40,'x1':60,'y0':20,'y1':80,'z0':40,'z1':50},'coil':{'x0':70,'x1':80,'y0':20,'y1':80,'z0':60,'z1':70},'heater':{'cpus':[{'x0':45,'x1':55,'y0':40,'y1':60}]},'layers':{'dielectric_mm':50},'mesh':{'dx_mm':10},'run':{'open_top':False}}


class LocalRefinementTests(unittest.TestCase):
    def test_conformal_axis_counts_and_original_unchanged(self):
        c=mesh_config();before=copy.deepcopy(c);base=build_mesh(c)
        c['mesh']['refinement_regions']=[{'name':'Local','shape':'box','unit':'mm','min':[10,10,10],'max':[40,40,40],'cell_size':{'value':5,'unit':'mm'}}]
        refined=build_mesh(c);self.assertGreater(refined[1],base[1]);self.assertEqual(refined[2:4],base[2:4]);self.assertEqual(before,mesh_config())
        boxes=refinement_boxes(c['mesh'],[100]*3);cuts,counts=refined_axis([0,100],0,10,boxes)
        self.assertEqual(cuts,[0,10,40,100]);self.assertEqual(counts,[2,6,6]);self.assertEqual(refined_axis([0,10,100],0,10,[]),([0,10,100],[2,9]))
    def test_invalid_regions_rejected_before_generation(self):
        c=mesh_config();r={'shape':'box','unit':'mm','min':[0,0,0],'max':[20,20,20],'cell_size':{'value':5,'unit':'mm'}}
        for key,value in [('max',[101,20,20]),('min',[0,float('nan'),0]),('cell_size',{'value':10,'unit':'mm'}),('cell_size',{'value':False,'unit':'mm'})]:
            bad=copy.deepcopy(r);bad[key]=value;c['mesh']['refinement_regions']=[bad]
            with self.assertRaises(ValueError):build_mesh(c)
    def test_shape_reference_tracks_dimensions_without_mutating_config(self):
        c=mesh_config();c['mesh']['refinement_regions']=[{'target_path':['board'],'cell_size':{'value':5,'unit':'mm'}}]
        original=copy.deepcopy(c);resolved=refinement_boxes(c['mesh'],[100]*3,c)
        self.assertEqual(resolved[0][:2],([c['board'][k+'0'] for k in 'xyz'],[c['board'][k+'1'] for k in 'xyz']))
        self.assertGreater(build_mesh(c)[1],build_mesh(mesh_config())[1]);self.assertEqual(c,original)
        c['board']['x1']+=1;self.assertEqual(refinement_boxes(c['mesh'],[100]*3,c)[0][1][0],c['board']['x1'])
        del c['board']
        with self.assertRaisesRegex(ValueError,'MESH-R001'):refinement_boxes(c['mesh'],[100]*3,c)

    def test_curved_target_envelope_and_invalid_references(self):
        from tmc49_full_tank.tools.mesh_refinement import geometry_box
        c={'regions':[{'shape':'cylinder','unit':'m','center':[1,2,3],'radius':.5,'height':2,'axis':'x'}]}
        self.assertEqual(geometry_box(c,['regions',0])['min'],[0,1.5,2.5])
        for path in [[],['regions',-1],['__proto__'],['regions','0']]:
            with self.assertRaises(ValueError):geometry_box(c,path)
        c['mesh']={'dx_mm':100,'refinement_regions':[{'target_path':['regions',0],'min':[0,0,0],'cell_size':{'value':.01,'unit':'m'}}]}
        with self.assertRaisesRegex(ValueError,'MESH-R003'):refinement_boxes(c['mesh'],[5000]*3,c)

    def test_silo_refinement_preserves_domain_and_local_z_spacing(self):
        from tests.test_silo_contract import draft,normalizer
        from tmc49_full_tank.tools.build_silo_runtime import block_mesh,mesh_plan
        c=draft();c['mesh']['target_cells']=4000;original,base=block_mesh(c)
        c['geometry']={'regions':[{'name':'Band','shape':'box','unit':'m','min':[-.1,-.1,.4],'max':[.1,.1,.6]}]}
        c['mesh']['refinement_regions']=[{'target_path':['geometry','regions',0],'cell_size':{'value':.03,'unit':'m'}}]
        ok,normalized,message=normalizer()(c);self.assertTrue(ok,message);self.assertEqual(normalized['mesh']['refinement_regions'],c['mesh']['refinement_regions']);self.assertEqual(normalized['geometry'],c['geometry'])
        text,plan=block_mesh(normalized);self.assertGreater(plan['actual_cells'],base['actual_cells'])
        for key in ['radius','height','grain','inlet_half','outer']:self.assertEqual(plan[key],base[key])
        self.assertEqual(plan['z_levels'],[0,.4,.6,1.,1.4])
        for a,b,n in zip(plan['z_levels'],plan['z_levels'][1:],plan['z_counts']):
            if a>=.4 and b<=.6:self.assertLessEqual((b-a)/n,.03)
        c['mesh']['maximum_cells']=100
        with self.assertRaisesRegex(ValueError,'MESH-R005'):mesh_plan(c)
        c['mesh'].pop('maximum_cells');c['mesh']['refinement_regions'][0]['cell_size']['value']=1e-300
        with self.assertRaisesRegex(ValueError,'MESH-R005'):mesh_plan(c)
        c['mesh']['refinement_regions']=[]
        self.assertEqual(block_mesh(c)[0],original)
        c['mesh']['refinement_regions']=[{'shape':'box','unit':'m','min':[.35,.35,0],'max':[.39,.39,.1],'cell_size':{'value':.03,'unit':'m'}}]
        with self.assertRaisesRegex(ValueError,'MESH-R004'):mesh_plan(c)

    def test_fill_cache_and_legacy_mapping_checked_on_server(self):
        c={'domain':{'shape':'box','unit':'m','min':[0,0,0],'max':[1,2,1]},'regions':[{'shape':'box','unit':'m','min':[0,.2,0],'max':[1,1.2,1],'fill':{'container_path':['domain'],'axis':'y','start':200,'end':1200,'unit':'mm'}}]}
        original=copy.deepcopy(c);validate_fill_definitions(c);self.assertEqual(c,original)
        c['regions'][0]['max'][1]=1.5
        with self.assertRaises(ValueError):validate_fill_definitions(c)
        c=original;c['domain']['material_state']='solid'
        with self.assertRaises(ValueError):validate_fill_definitions(c)

    def test_overlap_interior_and_direct_cli_fill_conflicts_rejected(self):
        from tmc49_full_tank.tools.mesh_refinement import validate_legacy_fills
        c={'domain':{'shape':'box','unit':'m','min':[0,0,0],'max':[1,2,1]},'regions':[{'shape':'box','unit':'m','min':[0,0,0],'max':[1,1.5,1],'fill':{'container_path':['domain'],'axis':'y','start':0,'end':1.5,'unit':'m'}}]}
        other=copy.deepcopy(c['regions'][0]);other['min'][1]=1;other['max'][1]=2;other['fill'].update(start=1,end=2);c['regions'].append(other)
        with self.assertRaisesRegex(ValueError,'겹칩니다'):validate_fill_definitions(c)
        c=mesh_config();c['dielectric_fluid']={'fill':{'container_path':['tank'],'axis':'y','start':0,'end':50,'unit':'mm'}};validate_legacy_fills(c)
        c['dielectric_fluid']['fill']['end']=60
        with self.assertRaises(ValueError):validate_legacy_fills(c)
        c={'domain':{'shape':'box','unit':'m','min':[0,0,0],'max':[1,2,1],'interior':{'shape':'box','unit':'m','min':[0,0,0],'max':[2,2,1]}}}
        with self.assertRaisesRegex(ValueError,'외곽'):validate_fill_definitions(c)

    def test_warehouse_local_refinement_preserves_geometry_and_restriction(self):
        import numpy as np
        from tracer_transport.porous_warehouse_mesh import generate_mesh,restrict_to_base
        spec={'geometry_spec':{'geometry':{'length_m':6,'width_m':4,'eaves_m':3,'roof_rise_m':1}},'loading':{'blocks':[{'min_m':[1,1,.5],'max_m':[2,3,2]}]},'porous_mesh':{'kind':'aligned_grain_blocks','base_max_spacing_m':[1,1,1],'refinement':1,'maximum_cells':100000}}
        _,base=generate_mesh(spec);original=copy.deepcopy(spec)
        spec['porous_mesh']['refinement_regions']=[{'name':'Local','shape':'box','unit':'m','min':[0,0,0],'max':[1,1,.5],'cell_size':{'value':.5,'unit':'m'}}]
        text,local=generate_mesh(spec);self.assertGreater(len(local['cell_volumes_m3']),len(base['cell_volumes_m3']));self.assertAlmostEqual(sum(local['cell_volumes_m3']),sum(base['cell_volumes_m3']))
        self.assertAlmostEqual(sum(local['cell_volumes_m3']*local['loaded_region']),sum(base['cell_volumes_m3']*base['loaded_region']))
        spec['porous_mesh']['refinement']=2;_,fine=generate_mesh(spec)
        np.testing.assert_allclose(restrict_to_base(fine['cell_centres_m'],fine['cell_volumes_m3'],fine['base_parent']),local['cell_centres_m'],atol=1e-12)
        bad=copy.deepcopy(spec);bad['porous_mesh']['refinement_regions'][0]['max'][2]=4
        with self.assertRaises(ValueError):generate_mesh(bad)
        self.assertNotIn('refinement_regions',original['porous_mesh'])

if __name__=='__main__':unittest.main()
