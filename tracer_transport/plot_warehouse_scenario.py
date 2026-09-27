"""Export plan-view concentration slices and calculated probe histories."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from matplotlib.patches import Rectangle


def render(case, output):
    case, output = Path(case), Path(output)
    spec = json.loads((case/'transport_input.json').read_text())
    with np.load(case/'concentration.npz', allow_pickle=False) as data:
        centres = data['cell_centres_m']
        fields = data['concentration']*1e6
        times = data['times_s']
        temperature = data['temperature_C']
    x, xi = np.unique(np.round(centres[:, 0], 8), return_inverse=True)
    y, yi = np.unique(np.round(centres[:, 1], 8), return_inverse=True)
    order = np.argsort(abs(centres[:, 2]-1.5))
    _, first = np.unique((yi*len(x)+xi)[order], return_index=True)
    indices = order[first].reshape(len(y), len(x))
    output.mkdir(parents=True, exist_ok=False)
    fig, axes = plt.subplots(3, 1, figsize=(13, 10), constrained_layout=True)
    for ax, index in zip(axes, [0, int(np.argmin(abs(times-86400))), len(times)-1]):
        img = ax.pcolormesh(x, y, fields[index, indices], shading='nearest', cmap='viridis', norm=LogNorm(vmin=.001, vmax=1))
        for block in spec['loading']['blocks']:
            lo, hi = block['min_m'], block['max_m']
            ax.add_patch(Rectangle(lo[:2], hi[0]-lo[0], hi[1]-lo[1], fill=False, edgecolor='white', linewidth=.75))
        ax.set(xlim=(0,78), ylim=(0,25), aspect='equal', xlabel='Length x (m)', ylabel='Width y (m)',
               title=f'{times[index]/3600:g} h | prescribed ambient temperature {temperature[index]:.2f} C')
    fig.colorbar(img, ax=axes, label='ClO2 gas concentration (mg/m3), logarithmic scale', shrink=.8)
    fig.suptitle('Plan-based assumed diffusion scenario | nearest cell-centre slice at z = 1.5 m\n12 porous blocks; still air; closed walls; reaction/leakage omitted', fontsize=13)
    fig.savefig(output/'concentration_slices.png', dpi=160)
    plt.close(fig)
    probes = [[4,12.5,1.5], [8,12.5,1.5], [8,10,1.5], [20,12.5,1.5]]
    cells = [int(np.argmin(np.linalg.norm(centres-p, axis=1))) for p in probes]
    with (output/'probe_timeseries.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['time_s', 'prescribed_temperature_C']+[f'P{i+1}_mg_m3' for i in range(len(probes))])
        writer.writerows([float(t),float(T)]+[float(fields[j,i]) for i in cells] for j,(t,T) in enumerate(zip(times,temperature)))
    fig, axes = plt.subplots(2,1,figsize=(11,7),constrained_layout=True)
    axes[0].plot(times/86400,temperature,color='#b95328')
    axes[0].set(ylabel='Prescribed temperature (C)',xlabel='Time (days)',title='Agrafioti et al. 2021 Fig.1 container 5: digitized ambient input')
    for i,(point,cell) in enumerate(zip(probes,cells)):
        axes[1].plot(times/86400,fields[:,cell],label=f'P{i+1} near {point} m')
    axes[1].set(yscale='log',ylabel='Calculated ClO2 (mg/m3)',xlabel='Time (days)',title='Calculated probe histories; no measured comparison')
    axes[1].legend(fontsize=8)
    for ax in axes: ax.grid(alpha=.2)
    fig.savefig(output/'temperature_and_probes.png',dpi=160)
    plt.close(fig)
    report={'case':str(case),'slice_target_z_m':1.5,
            'slice_actual_z_range_m':[float(centres[indices,2].min()),float(centres[indices,2].max())],
            'probes':[{'requested_m':p,'cell':c,'actual_m':centres[c].tolist(),'distance_m':float(np.linalg.norm(centres[c]-p))} for p,c in zip(probes,cells)],
            'initial_peak_mg_m3':float(fields[0].max()),'final_peak_mg_m3':float(fields[-1].max()),
            'physical_validation':False}
    (output/'plot_provenance.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    render(args.case,args.output)
