"""Offline figures for any completed structured tracer case; no browser or CFD calls."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from .sample import ConcentrationField


def concentration_figure(case):
    case=Path(case)
    cfg=json.loads((case/'config.json').read_text())
    verified=ConcentrationField(case/'concentration.npz')
    with np.load(case/'concentration.npz',allow_pickle=False) as data:
        times=verified.times
        nx,ny,nz=verified.shape.astype(int)
        lx,ly,lz=verified.lengths
        c=verified.c.reshape(len(times),nz,ny,nx)
        raw_q=data['sorbed_bulk']
        if raw_q.shape!=verified.c.shape or not np.isfinite(raw_q).all():
            raise ValueError('Invalid sorbed field for visualization')
        q=raw_q.reshape(c.shape)
    if cfg['shape_xyz']!=verified.shape.tolist() or not np.allclose(cfg['lengths_m'],verified.lengths):
        raise ValueError('Configuration and output geometry differ')
    fig,axes=plt.subplots(2,3,figsize=(12,5.4))
    fig.subplots_adjust(left=.065,right=.98,top=.87,bottom=.22,hspace=1.3,wspace=.25)
    indices=[0,len(times)//2,len(times)-1]
    y=ny//2
    for row,(field,label) in enumerate([(c,'Pore concentration C/C_ref'),(q,'Sorbed amount Q/C_ref (bulk basis)')]):
        vmin=float(field.min());vmax=float(field.max())
        if vmax-vmin<1e-12:
            vmax=vmin+max(.01,abs(vmin)*.01)
        for col,t in enumerate(indices):
            ax=axes[row,col]
            im=ax.imshow(field[t,:,y,:],origin='lower',extent=[0,lx,0,lz],
                         aspect='equal',interpolation='nearest',vmin=vmin,vmax=vmax,cmap='viridis')
            if cfg['kind']=='porous':
                for box in cfg['porous_boxes_m']:
                    lo,hi=box['min'],box['max']
                    if lo[1]<=(y+.5)*ly/ny<hi[1]:
                        ax.add_patch(Rectangle((lo[0],lo[2]),hi[0]-lo[0],hi[2]-lo[2],
                                               fill=False,edgecolor='white',linewidth=1))
            ax.set(title=f't={times[t]:g} s',xlabel='x [m]',ylabel='z [m]')
        color_axis=fig.add_axes([.32,.555 if row==0 else .095,.40,.025])
        fig.colorbar(im,cax=color_axis,label=label,orientation='horizontal')
    fig.suptitle(f'Normalized tracer, y={(y+.5)*ly/ny:g} m; white line: porous interface')
    return fig,axes


def plot_case(case, output=None):
    case=Path(case)
    output=case if output is None else Path(output)
    output.mkdir(parents=True,exist_ok=True)
    fig,_=concentration_figure(case)
    fig.savefig(output/'concentration_sorption.png',dpi=160)
    plt.close(fig)
    budget=np.loadtxt(case/'mass_balance.csv',delimiter=',',skiprows=1)
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    axes[0].plot(budget[:,0],budget[:,1],label='Gas')
    axes[0].plot(budget[:,0],budget[:,4],label='Sorbed')
    axes[0].plot(budget[:,0],budget[:,1]+budget[:,4],label='Total',ls='--')
    axes[0].set(xlabel='t [s]',ylabel='Inventory [C_ref m3]',title='Gas and sorbed inventory')
    axes[0].legend()
    axes[1].plot(budget[:,0],budget[:,-1])
    axes[1].set(xlabel='t [s]',ylabel='Balance error [C_ref m3]',title='Closed-system conservation')
    axes[1].ticklabel_format(axis='y',style='sci',scilimits=(0,0))
    fig.savefig(output/'sorption_balance.png',dpi=160)
    plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('case',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    plot_case(args.case,args.output)
