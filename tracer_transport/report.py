"""Generate numerical checks and figures from completed verification results."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .sample import ConcentrationField


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    root=parser.parse_args().root
    summary=json.loads((root/'summary.json').read_text())
    case=root/'porous_80_0.0025'
    cfg=json.loads((case/'config.json').read_text())
    field=ConcentrationField(case/'concentration.npz')
    nx,ny,nz=field.shape
    lx,ly,lz=field.lengths
    values=field.c.reshape((-1,nz,ny,nx))
    fig,axes=plt.subplots(1,3,figsize=(13,3.6),layout='constrained')
    for ax,idx in zip(axes,[0,len(field.times)//2,-1]):
        im=ax.imshow(values[idx,nz//2],origin='lower',extent=[0,lx,0,ly],aspect='auto',vmin=float(values.min()),vmax=float(values.max()),cmap='viridis')
        for edge in cfg['porous_x_fraction']:
            ax.axvline(edge*lx,color='white',ls='--')
        ax.set(title=f't={field.times[idx]:g} s; z={(nz//2+.5)*lz/nz:g} m',xlabel='x [m]',ylabel='y [m]')
    fig.colorbar(im,ax=axes,label='Pore concentration C/C_ref')
    fig.suptitle('Numerical tracer benchmark: air | porous slab | air')
    fig.savefig(root/'concentration.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    for fraction in [.1,.4,.9]:
        x=fraction*lx
        reg=field.sample_concentration([x,ly/2,lz/2],field.times[0])['region_id']
        y=[field.sample_concentration([x,ly/2,lz/2],t,reg)['concentration'] for t in field.times]
        axes[0].plot(field.times,y,label=f'x={x} m, region {reg}')
    axes[0].set(xlabel='t [s]',ylabel='C/C_ref',title='Fixed-point concentration');axes[0].legend()
    for row in summary:
        data=np.loadtxt(root/row['case']/'mass_balance.csv',delimiter=',',skiprows=1)
        axes[1].plot(data[:,0],data[:,-1]/data[0,1],label=row['case'])
    axes[1].set(xlabel='t [s]',ylabel='(M-M0)/M0',title='Closed-domain mass balance')
    axes[1].ticklabel_format(axis='y',style='sci',scilimits=(0,0))
    fig.savefig(root/'history_balance.png',dpi=160);plt.close(fig)
    checks={}
    checks['uniform_path_integral']=True
    uniform=ConcentrationField(root/'uniform_20_0.01/concentration.npz')
    ts=np.linspace(uniform.times[0],uniform.times[-1],101)
    vals=[uniform.sample_concentration([(.1+.8*s)*lx,ly/2,lz/2],t)['concentration'] for s,t in zip(np.linspace(0,1,101),ts)]
    integral=float(np.trapezoid(vals,ts))
    checks['uniform_path_integral_value_Cref_s']=integral
    checks['uniform_path_integral']=bool(abs(integral-cfg['initial_mean']*(ts[-1]-ts[0]))<1e-10)
    checks['invalid_queries']=all(not field.sample_concentration(p,t,r)['valid'] for p,t,r in
                                 [([-1,0,0],0,None),([lx/2,ly/2,lz/2],field.times[-1]+1,None),
                                  ([lx/2,ly/2,lz/2],0,99),([float('nan'),0,0],0,None)])
    spatial=[r['analytic_rmse'] for r in summary if r['case'] in ['diffusion_20_0.01','diffusion_40_0.01','diffusion_80_0.01']]
    temporal=[r['analytic_rmse'] for r in summary if r['case'] in ['diffusion_80_0.01','diffusion_80_0.005','diffusion_80_0.0025']]
    checks['spatial_errors']=spatial;checks['temporal_errors']=temporal
    checks['spatial_convergence']=bool(np.all(np.diff(spatial)<0))
    checks['temporal_convergence']=bool(np.all(np.diff(temporal)<0))
    profiles=[]
    for n,dt in [(20,.01),(40,.005),(80,.0025)]:
        f=ConcentrationField(root/f'porous_{n}_{dt:g}/concentration.npz')
        profiles.append(f.c[-1].reshape(nz,ny,n).mean(axis=(0,1)))
    d1=float(np.sqrt(np.mean((profiles[0]-profiles[1].reshape(20,2).mean(axis=1))**2)))
    d2=float(np.sqrt(np.mean((profiles[1]-profiles[2].reshape(40,2).mean(axis=1))**2)))
    checks['porous_joint_refinement_l2']=[d1,d2]
    checks['porous_joint_convergence']=d2<d1
    (root/'integration_checks.json').write_text(json.dumps(checks,indent=2))
    if not all(checks[k] for k in ['uniform_path_integral','invalid_queries','spatial_convergence','temporal_convergence','porous_joint_convergence']):
        raise RuntimeError('Convergence or query check failed')
    print(json.dumps(checks,indent=2))


if __name__=='__main__':
    main()
