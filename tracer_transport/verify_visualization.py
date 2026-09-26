"""Independent ASCII OpenFOAM/mesh-to-NPZ-to-figure audit. Does not launch a browser."""
import argparse
import json
from pathlib import Path
import re
import numpy as np
from .plot_case import concentration_figure, plot_case, plt


def foam_text(path):
    text=path.read_text()
    text=re.sub(r'/\*.*?\*/','',text,flags=re.S)
    return re.sub(r'//[^\n]*','',text)


def mesh_list(path):
    text=foam_text(path)
    body=re.split(r'FoamFile\s*\{.*?\}',text,maxsplit=1,flags=re.S)[-1].strip()
    match=re.fullmatch(r'(\d+)\s*\((.*)\)\s*',body,flags=re.S)
    if not match:
        raise ValueError(f'Unsupported mesh list {path}')
    return int(match[1]),match[2]


def cell_centres(mesh,n):
    size,text=mesh_list(mesh/'points')
    points=np.array([np.fromstring(v,sep=' ') for v in re.findall(r'\(([^()]*)\)',text)])
    if points.shape!=(size,3):
        raise ValueError('Invalid points')
    size,text=mesh_list(mesh/'faces')
    faces=re.findall(r'(\d+)\s*\(([^()]*)\)',text)
    if len(faces)!=size or any(int(k)!=4 for k,_ in faces):
        raise ValueError('Audit only supports generated Cartesian hexahedra')
    face_indices=np.array([np.fromstring(v,sep=' ',dtype=int) for _,v in faces])
    centres=points[face_indices].mean(axis=1)
    size,text=mesh_list(mesh/'owner');owner=np.fromstring(text,sep=' ',dtype=int)
    if len(owner)!=size or size!=len(faces):
        raise ValueError('Invalid owner list')
    size,text=mesh_list(mesh/'neighbour');neighbour=np.fromstring(text,sep=' ',dtype=int)
    if len(neighbour)!=size:
        raise ValueError('Invalid neighbour list')
    result=np.zeros((n,3));counts=np.zeros(n)
    for ids,values in [(owner,centres),(neighbour,centres[:len(neighbour)])]:
        np.add.at(result,ids,values);np.add.at(counts,ids,1)
    if not np.all(counts==6):
        raise ValueError('Expected six faces per Cartesian cell')
    return result/counts[:,None]


def scalar_field(path,n):
    text=foam_text(path)
    tokens=text[text.index('internalField')+len('internalField'):text.index('boundaryField')].strip()
    if tokens.startswith('uniform '):
        return np.full(n,float(tokens[len('uniform '):].strip().rstrip(';')))
    match=re.fullmatch(r'nonuniform\s+List<scalar>\s+(\d+)\s*\((.*?)\)\s*;',tokens,flags=re.S)
    if not match or int(match[1])!=n:
        raise ValueError(f'Invalid scalar data: {path}')
    values=np.array([float(s) for s in match[2].split()])
    if values.shape!=(n,) or not np.isfinite(values).all():
        raise ValueError('Invalid scalar count or values')
    return values


def audit(case,output):
    case=Path(case);output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    cfg=json.loads((case/'config.json').read_text())
    with np.load(case/'concentration.npz',allow_pickle=False) as archive:
        d={k:archive[k].copy() for k in archive.files}
    nx,ny,nz=d['shape_xyz'];lx,ly,lz=d['lengths_m'];n=int(nx*ny*nz)
    centres=cell_centres(case/'constant/polyMesh',n)
    z,y,x=np.meshgrid((np.arange(nz)+.5)*lz/nz,(np.arange(ny)+.5)*ly/ny,
                      (np.arange(nx)+.5)*lx/nx,indexing='ij')
    expected=np.column_stack([x.ravel(),y.ravel(),z.ravel()])
    coordinate_error=float(np.max(np.abs(centres-expected)))
    raw_c=[];raw_q=[]
    for t in d['times']:
        raw_c.append(scalar_field(case/f'{t:g}'/'C',n))
        raw_q.append(scalar_field(case/f'{t:g}'/'Q',n))
    raw_c=np.asarray(raw_c);raw_q=np.asarray(raw_q)
    c_error=float(np.max(np.abs(raw_c-d['concentration'])))
    q_error=float(np.max(np.abs(raw_q-d['sorbed_bulk'])))
    region=np.zeros(n,dtype=int)
    if cfg['kind']=='porous':
        for box in cfg['porous_boxes_m']:
            region[np.all((centres>=box['min'])&(centres<box['max']),axis=1)]=1
    expected_times=np.arange(round(cfg['end_s']/cfg['write_interval_s'])+1)*cfg['write_interval_s']
    timeline=len(expected_times)==len(d['times']) and np.allclose(expected_times,d['times'],rtol=0,atol=1e-9)
    eps=scalar_field(case/'0/eps',n)
    volume=lx*ly*lz/n
    totals=(raw_c*eps+raw_q).sum(axis=1)*volume
    budget=np.loadtxt(case/'mass_balance.csv',delimiter=',',skiprows=1)
    budget_error=0.
    for t,total in zip(d['times'],totals):
        rows=budget[np.isclose(budget[:,0],t,atol=1e-9,rtol=0)]
        if not len(rows):
            raise ValueError('Missing mass log at a plotted time')
        budget_error=max(budget_error,float(np.max(np.abs(rows[:,1]+rows[:,4]-total))))
    fig,axes=concentration_figure(case)
    figure_ok=True
    snapshots=[0,len(d['times'])//2,len(d['times'])-1]
    yy=ny//2
    for row,field in enumerate([raw_c,raw_q]):
        array=field.reshape(len(d['times']),nz,ny,nx)
        norms=[]
        for col,index in enumerate(snapshots):
            ax=axes[row,col];im=ax.images[0]
            figure_ok &= (np.array_equal(np.asarray(im.get_array()),array[index,:,yy,:])
                          and im.origin=='lower' and ax.get_aspect()==1.0
                          and im.get_interpolation()=='nearest'
                          and np.allclose(im.get_extent(),[0,lx,0,lz]))
            norms.append((im.norm.vmin,im.norm.vmax))
            expected_boxes=[b for b in cfg['porous_boxes_m'] if cfg['kind']=='porous' and b['min'][1]<=(yy+.5)*ly/ny<b['max'][1]]
            figure_ok &= len(ax.patches)==len(expected_boxes)
            for rect,box in zip(ax.patches,expected_boxes):
                lo,hi=box['min'],box['max']
                figure_ok &= np.allclose([rect.get_x(),rect.get_y(),rect.get_width(),rect.get_height()],
                                        [lo[0],lo[2],hi[0]-lo[0],hi[2]-lo[2]])
        figure_ok &= all(pair==norms[0] for pair in norms)
    plt.close(fig)
    result={'cells':n,'frames':len(d['times']),'raw_C_to_npz_max_error':c_error,
            'raw_Q_to_npz_max_error':q_error,'mesh_centres_xyz_max_error_m':coordinate_error,
            'region_tags_match':bool(np.array_equal(region,d['region_id'])),
            'timeline_complete':bool(timeline),'raw_inventory_to_budget_max_error':budget_error,
            'figure_values_axes_colors_boundaries_match':bool(figure_ok),
            'time_change_max_C':float(np.max(np.abs(raw_c[-1]-raw_c[0]))),
            'min_Q_outside_porous':float(raw_q[:,region==0].min()) if np.any(region==0) else None,
            'max_Q_outside_porous':float(raw_q[:,region==0].max()) if np.any(region==0) else None,
            'scope':'static x-z slice only; no Studio playback integration'}
    result['pass']=bool(c_error<=1e-13 and q_error<=1e-13 and coordinate_error<=1e-12
                        and result['region_tags_match'] and timeline and budget_error<=1e-12 and figure_ok)
    (output/'visualization_audit.json').write_text(json.dumps(result,indent=2))
    plot_case(case,output)
    print(json.dumps(result,indent=2))
    if not result['pass']:
        raise RuntimeError('Visualization audit failed')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('case',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    audit(args.case,args.output)
