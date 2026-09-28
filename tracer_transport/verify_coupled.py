"""Independent analytical tests for energy storage and viscous velocity decay.

Artificial numerical inputs, not a warehouse or chemical validation.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from .warehouse_coupled import generate, read_vector
from .warehouse_case import write_scalar
from .warehouse_scenario import PATCHES
from .mesh_centres import cell_centres
from .run import header, run_command, read_field


def run_test(root, kind, resolution, dt):
    spec = json.loads(Path(__file__).with_name('warehouse_coupled_pilot.json').read_text())
    spec['geometry_spec']['mesh'].update(nx=20, ny_per_half=2, nz=2)
    case = root/f'{kind}_{resolution}_{str(dt).replace(".","p")}'
    generate(spec,case)
    # Replace the preparatory gabled mesh definition, retain its log as provenance.
    # A separate new mesh is generated inside this new, test-owned case only.
    import shutil
    (case/'log.blockMesh').rename(case/'log.preparatoryBlockMesh')
    (case/'log.checkMesh').rename(case/'log.preparatoryCheckMesh')
    shutil.rmtree(case/'constant/polyMesh')
    length, width, height = 1., 2., 1.
    nx, ny, nz = (resolution,4,2) if kind=='energy' else (4,resolution,2)
    sides = 'type wall; faces ((0 1 5 4)(3 7 6 2));'
    # x ends are cyclic for both benchmarks; remaining faces are physical walls.
    (case/'system/blockMeshDict').write_text(header('blockMeshDict')+f'''
scale 1;
vertices ((0 0 0)(1 0 0)(1 2 0)(0 2 0)(0 0 1)(1 0 1)(1 2 1)(0 2 1));
blocks (hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1));
edges ();
boundary (
 floor {{ type wall; faces ((0 3 2 1)); }}
 roof {{ type wall; faces ((4 5 6 7)); }}
 sideWalls {{ {sides} }}
 endWall {{ type cyclic; neighbourPatch annexInterface; faces ((0 4 7 3)); }}
 annexInterface {{ type cyclic; neighbourPatch endWall; faces ((1 2 6 5)); }}
);
mergePatchPairs ();
''')
    for cmd in ('blockMesh','checkMesh'):run_command(case,cmd)
    count=nx*ny*nz
    xyz=cell_centres(case/'constant/polyMesh',count)
    # Isotropic artificial parameters and no buoyancy isolate each PDE.
    for name,value,dims in [('C',1.,'0 0 0 0 0 0 0'),('eps',1.,'0 0 0 0 0 0 0'),
        ('drag',0.,'0 0 -1 0 0 0 0'),('heatCapacityRatio',2.,'0 0 0 0 0 0 0'),
        ('alphaBulk',.01,'0 2 -1 0 0 0 0'),('diffusionFactor',1.,'0 0 0 0 0 0 0'),('freeGas',1.,'0 0 0 0 0 0 0')]:
        write_scalar(case/'0',name,np.full(count,value),dims,PATCHES)
    t0=296.15+np.cos(2*np.pi*xyz[:,0]) if kind=='energy' else np.full(count,296.15)
    write_scalar(case/'0','T',t0,'0 0 0 1 0 0 0',PATCHES)
    uniform_velocity=np.zeros((count,3))
    if kind=='momentum':uniform_velocity[:,0]=.01*np.sin(np.pi*xyz[:,1]/2)
    vector_text='\n'.join('('+' '.join(f'{v:.16g}' for v in row)+')' for row in uniform_velocity)
    bcs='\n'.join(f'{p} {{ '+ ('type cyclic;' if p in ('endWall','annexInterface') else 'type fixedValue; value uniform (0 0 0);' if p=='sideWalls' else 'type slip;')+' }' for p in PATCHES)
    (case/'0/U').write_text(header('U','volVectorField')+f'dimensions [0 1 -1 0 0 0 0]; internalField nonuniform List<vector> {count} (\n{vector_text}\n); boundaryField {{\n{bcs}\n}}')
    # Replace cyclic patch boundary dictionaries on all scalar fields, including p.
    import re
    for p in (case/'0').iterdir():
        if p.name=='U':continue
        text=p.read_text()
        for patch in ('endWall','annexInterface'):
            text=re.sub(patch+r'\s*\{[^}]*\}',patch+' { type cyclic; }',text)
        p.write_text(text)
    for name,dims,value in [('p_rgh','0 2 -2 0 0 0 0',0),('alphat','0 2 -1 0 0 0 0',0)]:
        bcs='\n'.join(f'{p} {{ type '+('cyclic;' if p in ('endWall','annexInterface') else 'zeroGradient;')+' }' for p in PATCHES)
        (case/'0'/name).write_text(header(name,'volScalarField')+f'dimensions [{dims}]; internalField uniform {value}; boundaryField {{ {bcs} }}')
    (case/'constant/turbulenceProperties').write_text(header('turbulenceProperties')+'simulationType laminar;')
    (case/'constant/g').write_text(header('g','uniformDimensionedVectorField')+'dimensions [0 1 -2 0 0 0 0]; value (0 0 0);')
    (case/'constant/transportProperties').write_text(header('transportProperties')+'transportModel Newtonian; nu 0.1; beta 0.003; TRef 296.15; Pr 0.71; Prt 0.85;')
    (case/'system/controlDict').write_text(header('controlDict')+f'''
application warehouseBuoyantFoam; startFrom startTime; startTime 0; stopAt endTime; endTime 1;
deltaT {dt}; adjustTimeStep no; writeControl runTime; writeInterval 1;
writeFormat ascii; writePrecision 16; timeFormat general; timePrecision 12; runTimeModifiable false;
''')
    provenance={'kind':'artificial_analytical_'+kind,'shape':[nx,ny,nz],'dt_s':dt,'end_s':1,
        'geometry':'1 x 2 x 1 m rectangular periodic-x box, numerical test only',
        'expected':'T=296.15+cos(2pi*x)*exp(-0.005*(2pi)^2*t)' if kind=='energy' else 'Ux=0.01*sin(pi*y/2)*exp(-0.1*(pi/2)^2*t)',
        'warehouse_validation':False}
    # The numerical fixture is deliberately not eligible for the warehouse viewer.
    (case/'model_contract.json').write_text(json.dumps(provenance,indent=2))
    (case/'transport_input.json').write_text(json.dumps(provenance,indent=2))
    import hashlib
    files=[p for folder in ('0','system','constant') for p in (case/folder).rglob('*') if p.is_file()]
    (case/'input_hashes.json').write_text(json.dumps({str(p.relative_to(case)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2))
    run_command(case,'warehouseBuoyantFoam')
    U=read_vector(case/'1/U',count); T=read_field(case/'1/T',count); C=read_field(case/'1/C',count)
    exact = 296.15+np.cos(2*np.pi*xyz[:,0])*np.exp(-.005*(2*np.pi)**2) if kind=='energy' else .01*np.sin(np.pi*xyz[:,1]/2)*np.exp(-.1*(np.pi/2)**2)
    values = T if kind=='energy' else U[:,0]
    error=float(np.sqrt(np.mean((values-exact)**2)))
    normalized_error=error/(1 if kind=='energy' else .01)
    stationary_error=float(abs(U).max()) if kind=='energy' else float(abs(T-296.15).max())
    result={**provenance,'rmse':error,'relative_amplitude_rmse':normalized_error,
        'stationary_field_error':stationary_error,'uniform_tracer_error':float(abs(C-1).max()),
        'pass':bool(normalized_error < .002 and stationary_error < 1e-6 and abs(C-1).max()<1e-8)}
    (case/'checks.json').write_text(json.dumps(result,indent=2))
    (case/'state.json').write_text(json.dumps({'status':'complete' if result['pass'] else 'failed'}))
    return result


def execute(out):
    out=Path(out)
    out.mkdir(parents=True,exist_ok=False)
    results=[run_test(out,k,n,dt) for k in ('energy','momentum') for n,dt in ((20,.01),(40,.005))]
    report={'tests':results,'pass':all(r['pass'] for r in results), 'warehouse_convergence':False}
    (out/'report.json').write_text(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(execute(parser.parse_args().output),indent=2))
