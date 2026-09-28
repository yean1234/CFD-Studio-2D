"""Export scientific U/T/C section plots from saved coupled solver fields."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


def plot(case):
    case=Path(case)
    spec=json.loads((case/'transport_input.json').read_text())
    with np.load(case/'concentration.npz',allow_pickle=False) as a:
        xyz=a['cell_centres_m']; C=a['concentration'][-1]*1e6; T=a['temperature_K'][-1]-273.15; U=a['velocity_m_s'][-1]; times=a['times_s']; allc=a['concentration']*1e6; allt=a['temperature_K']-273.15; allu=a['velocity_m_s']
    speed=np.linalg.norm(U,axis=1)
    parameter_xyz=xyz.copy()
    if (case/'mesh_layout.npz').exists():
        with np.load(case/'mesh_layout.npz',allow_pickle=False) as layout:
            bounds=layout['bounds'];parameter_xyz[:,0]=(bounds[:,0]+bounds[:,1])/2;parameter_xyz[:,1]=(bounds[:,2]+bounds[:,3])/2
    # One nearest cell in each (x,y) column for an approximately horizontal section.
    columns={}
    for i,(x,y,z) in enumerate(parameter_xyz):
        key=(round(float(x),6),round(float(y),6))
        if key not in columns or abs(z-1.5)<abs(xyz[columns[key],2]-1.5):columns[key]=i
    horizontal=np.array(list(columns.values()))
    ys=np.unique(parameter_xyz[:,1]); y=ys[np.argmin(abs(ys-spec['geometry_spec']['geometry']['width_m']/2))]
    vertical=np.flatnonzero(np.isclose(parameter_xyz[:,1],y,atol=1e-8))
    fig,axes=plt.subplots(2,3,figsize=(17,7),layout='constrained')
    for row,(idx,dim,label) in enumerate(((horizontal,1,'Nearest cells to z=1.5 m'),(vertical,2,f'y={y:.3f} m'))):
        for col,(values,title,unit,cmap) in enumerate(((C,'ClO2 concentration','mg/m3','viridis'),(T,'Temperature','deg C','coolwarm'),(speed,'Superficial velocity magnitude','m/s','magma'))):
            ax=axes[row,col]
            graphic=ax.tricontourf(xyz[idx,0],xyz[idx,dim],values[idx],levels=20,cmap=cmap)
            fig.colorbar(graphic,ax=ax,label=unit,shrink=.75)
            ax.set_title(title+'\n'+label);ax.set_xlabel('x (m)');ax.set_ylabel('y (m)' if dim==1 else 'z (m)')
            ax.set_aspect('equal')
            if col==2:
                arrows=idx[::max(1,len(idx)//100)]
                ax.quiver(xyz[arrows,0],xyz[arrows,dim],U[arrows,0],U[arrows,dim],color='cyan',scale=max(speed.max()*15,.001),width=.003)
            for block in spec['loading']['blocks']:
                lo,hi=block['min_m'],block['max_m']
                if dim==1 or lo[1]<=y<=hi[1]:
                    ax.add_patch(Rectangle((lo[0],lo[dim]),hi[0]-lo[0],hi[dim]-lo[dim],fill=False,edgecolor='white',linewidth=.6,linestyle='--'))
    fig.suptitle(f'Coupled warehouse scenario | t={times[-1]:g} s | {len(xyz):,} cells\nAssumed properties and boundary conditions; no experimental or grid-convergence validation',fontsize=13)
    dest=case/'figures';dest.mkdir(exist_ok=True)
    fig.savefig(dest/'coupled_fields.png',dpi=150);plt.close(fig)
    requests=np.array([[4,12.5,1.5],[39,12.5,1.5],[74,12.5,1.5]])
    indices=np.array([np.argmin(np.linalg.norm(xyz-q,axis=1)) for q in requests])
    fig,axes=plt.subplots(3,1,figsize=(10,8),sharex=True,layout='constrained')
    for j,i in enumerate(indices):
        label='cell '+', '.join(f'{v:.2f}' for v in xyz[i])+' m'
        for ax,values in zip(axes,(allc[:,i],allt[:,i],np.linalg.norm(allu[:,i],axis=1))):ax.plot(times/60,values,label=label)
    for ax,unit in zip(axes,('ClO2 (mg/m3)','Temperature (deg C)','Speed (m/s)')):ax.set_ylabel(unit);ax.grid(alpha=.2)
    axes[0].legend(fontsize=8);axes[-1].set_xlabel('Simulated time (min)')
    fig.suptitle('Calculated cell histories (not measured inputs)')
    fig.savefig(dest/'coupled_probes.png',dpi=150);plt.close(fig)
    rows=[]
    for j,i in enumerate(indices):
        for k,t in enumerate(times):rows.append([j,int(i),*xyz[i],float(np.linalg.norm(xyz[i]-requests[j])),t,allc[k,i],allt[k,i],*allu[k,i]])
    np.savetxt(dest/'coupled_probes.csv',rows,delimiter=',',header='probe,cell_index,x_m,y_m,z_m,distance_from_requested_m,time_s,C_mg_m3,T_C,Ux_m_s,Uy_m_s,Uz_m_s',comments='')
    return str(dest)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('case',type=Path)
    print(plot(p.parse_args().case))
