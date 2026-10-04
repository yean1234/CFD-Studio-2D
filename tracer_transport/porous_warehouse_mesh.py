"""Nested multiblock meshes fitted to the idealized grain-stack boundaries.

No individual sack membranes are resolved. Every block envelope has the same
physical volume at every refinement. New cases only; no existing output edits.
"""
import math
from pathlib import Path
from .warehouse_geometry import header
from .warehouse_symmetry import symmetry_domain, PATCH


def _planned_layout(spec):
    g=spec['geometry_spec']['geometry']; m=spec['porous_mesh']
    if m.get('kind')!='aligned_grain_blocks':raise ValueError('Unknown porous mesh kind')
    r=m['refinement']
    if type(r) is not int or r<1:raise ValueError('Refinement must be a positive integer')
    spacing=m['base_max_spacing_m']
    if not isinstance(spacing,(list,tuple)) or len(spacing)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in spacing):
        raise ValueError('Invalid base spacing')
    blocks=spec['loading']['blocks']
    if not blocks:raise ValueError('At least one grain block is required')
    lows={b['min_m'][2] for b in blocks}; highs={b['max_m'][2] for b in blocks}
    if len(lows)!=1 or len(highs)!=1:raise ValueError('Aligned mesh requires common stack base and top')
    bottom,top=next(iter(lows)),next(iter(highs))
    if not 0<bottom<top<g['eaves_m']:raise ValueError('Stack levels must be below the eaves')
    x=sorted({0.,g['length_m'],*(b[k][0] for b in blocks for k in ('min_m','max_m'))})
    y=sorted({0.,g['width_m']/2,g['width_m'],*(b[k][1] for b in blocks for k in ('min_m','max_m'))})
    xd=[b-a for a,b in zip(x,x[1:])]
    yd=[b-a for a,b in zip(y,y[1:])]
    xc=[math.ceil(v/spacing[0]) for v in xd]
    yc=[math.ceil(v/spacing[1]) for v in yd]
    zc=[math.ceil(v/spacing[2]) for v in [bottom,top-bottom,g['eaves_m']+g['roof_rise_m']-top]]
    target=m.get('maximum_cell_edge_m')
    if target is not None:
        if isinstance(target,bool) or not isinstance(target,(int,float)) or not math.isfinite(target) or target<=0:
            raise ValueError('maximum_cell_edge_m must be finite and positive')
        # Roof edges slope in y. Limit physical edge length, not its projection.
        roof_factor=math.hypot(1,2*g['roof_rise_m']/g['width_m'])
        def capped_counts(lengths,existing):
            return [max(int(n),math.ceil(float(length)/target/r)) for length,n in zip(lengths,existing)]
        xc=capped_counts(xd,xc)
        yc=capped_counts([v*roof_factor for v in yd],yc)
        zc=capped_counts([bottom,top-bottom,g['eaves_m']+g['roof_rise_m']-top],zc)
    from .local_mesh_refinement import refine_counts
    xc,yc,zc=refine_counts(spec,x,y,[0.,bottom,top],xc,yc,zc)
    domain = symmetry_domain(spec)
    if domain:
        lower,upper = domain['bounds_m'][1]
        keep = [i for i,(a,b) in enumerate(zip(y,y[1:])) if a>=lower and b<=upper]
        yc = [yc[i] for i in keep]
        y = [v for v in y if lower<=v<=upper]
    # Python integers prevent overflow for a millimetre-scale whole building.
    cells=sum(map(int,xc))*sum(map(int,yc))*sum(map(int,zc))*r**3
    if type(m['maximum_cells']) is not int or m['maximum_cells']<1:
        raise ValueError('maximum_cells must be a positive integer')
    return g,x,y,[0.,bottom,top],xc,yc,zc,r,cells


def mesh_plan(spec):
    """Estimate counts and edge bounds without allocating any per-cell arrays."""
    g,x,y,z,xc,yc,zc,r,cells=_planned_layout(spec)
    dx=max(float(b-a)/(int(n)*r) for a,b,n in zip(x,x[1:],xc))
    dy=max(float(b-a)/(int(n)*r) for a,b,n in zip(y,y[1:],yc))
    dz=max(float(h)/(int(n)*r) for h,n in zip(
        [z[1],z[2]-z[1],g['eaves_m']+g['roof_rise_m']-z[2]],zc))
    edge=max(dx,dy*math.hypot(1,2*g['roof_rise_m']/g['width_m']),dz)
    target=spec['porous_mesh'].get('maximum_cell_edge_m')
    return {
        'cells':cells,
        'axis_cells':[sum(map(int,v))*r for v in (xc,yc,zc)],
        'maximum_axis_spacing_m':[dx,dy,dz],
        'maximum_cell_edge_m':edge,
        'requested_maximum_cell_edge_m':target,
        'planned_edge_requirement_met':None if target is None else edge<=target*(1+1e-12),
        'maximum_cells':spec['porous_mesh']['maximum_cells'],
        'within_cell_budget':cells<=spec['porous_mesh']['maximum_cells'],
        'one_scalar_float64_bytes':cells*8,
        'five_components_float64_bytes':cells*40,
        'memory_basis':'Five float64 components only (one vector and two scalars); excludes mesh, pressure, turbulence, matrix, temporary arrays and output. Not a solver RAM estimate.',
        'mesh_generated':False,'cfd_executed':False,
        'computational_domain':symmetry_domain(spec),
    }


def layout(spec):
    result=_planned_layout(spec)
    cells=result[-1];budget=spec['porous_mesh']['maximum_cells']
    if cells>budget:
        raise ValueError(f'Aligned mesh requires {cells:,} cells; exceeds explicit cell budget {budget:,}. No mesh allocated; do not silently coarsen the requested spacing.')
    return result


def generate_mesh(spec):
    import numpy as np
    g,x,y,z,xc,yc,zc,r,cells=layout(spec)
    domain = symmetry_domain(spec)
    ny=len(y);nx=len(x)
    def roof(yy):return g['eaves_m']+g['roof_rise_m']*(1-abs(2*yy/g['width_m']-1))
    def point(i,j,k):return k*nx*ny+j*nx+i
    vertices=[(xx,yy,z[k] if k<3 else roof(yy)) for k in range(4) for yy in y for xx in x]
    boundaries={p:[] for p in ('floor','roof','sideWalls','endWall','annexInterface')}
    if domain:boundaries[PATCH]=[]
    foam_blocks=[];centres=[];volumes=[];bounds=[];parents=[];half_parents=[];regions=[]
    base_offset=0
    for k in range(3):
      for j in range(ny-1):
       for i in range(nx-1):
        ids=[point(i,j,k),point(i+1,j,k),point(i+1,j+1,k),point(i,j+1,k),point(i,j,k+1),point(i+1,j,k+1),point(i+1,j+1,k+1),point(i,j+1,k+1)]
        shape=(int(xc[i]*r),int(yc[j]*r),int(zc[k]*r))
        foam_blocks.append('hex ('+' '.join(map(str,ids))+') ('+' '.join(map(str,shape))+') simpleGrading (1 1 1)')
        def face(p,indices):boundaries[p].append('('+' '.join(str(ids[v]) for v in indices)+')')
        if k==0:face('floor',[0,3,2,1])
        if k==2:face('roof',[4,5,6,7])
        if j==0:face(PATCH if domain and domain['mode']=='symmetry_y_max' else 'sideWalls',[0,1,5,4])
        if j==ny-2:face(PATCH if domain and domain['mode']=='symmetry_y_min' else 'sideWalls',[3,7,6,2])
        if i==0:face('endWall',[0,4,7,3])
        if i==nx-2:face('annexInterface',[1,2,6,5])
        sx,sy,sz=shape
        iz,iy,ix=np.meshgrid(np.arange(sz),np.arange(sy),np.arange(sx),indexing='ij')
        ix=ix.ravel();iy=iy.ravel();iz=iz.ravel()
        dx=(x[i+1]-x[i])/sx;dy=(y[j+1]-y[j])/sy
        xlo=x[i]+ix*dx;ylo=y[j]+iy*dy
        ym=ylo+dy/2;xm=xlo+dx/2
        if k<2:
            anchor=z[k];height=np.full(len(ix),z[k+1]-z[k]);slope=0.
        else:
            anchor=z[2];height=np.array([roof(v)-anchor for v in ym]);slope=2*g['roof_rise_m']/g['width_m']*(1 if y[j]<g['width_m']/2 else -1)
        s0=iz/sz;s1=(iz+1)/sz
        vol=dx*dy*height/sz
        # Exact centroids for a hexahedron between linear z(y) surfaces.
        cy=ym+slope*dy*dy/(12*height)
        cz=anchor+(s0+s1)/2*(height+slope*slope*dy*dy/(12*height))
        xyz=np.column_stack([xm,cy,cz]);centres.append(xyz);volumes.append(vol)
        # y-dependent bounds: z=anchor+s*(height_at_y_mid+slope*(y-y_mid)).
        bounds.append(np.column_stack([xlo,xlo+dx,ylo,ylo+dy,np.full(len(ix),anchor),s0,s1,height,np.full(len(ix),slope)]))
        parent=base_offset+((iz//r)*int(yc[j])+iy//r)*int(xc[i])+ix//r
        parents.append(parent)
        if r%2==0:
            cr=r//2
            half_parents.append(base_offset*cr**3+((iz//2)*int(yc[j]*cr)+iy//2)*int(xc[i]*cr)+ix//2)
        else:
            half_parents.append(parent)
        base_offset+=int(xc[i]*yc[j]*zc[k])
        loaded=np.zeros(len(ix),bool)
        for b in spec['loading']['blocks']:
            loaded |= np.all((xyz>=b['min_m'])&(xyz<b['max_m']),axis=1)
        regions.append(loaded)
    text=header('blockMeshDict')+'scale 1;\nvertices (\n'+'\n'.join('(%g %g %g)'%v for v in vertices)+'\n);\nblocks (\n'+'\n'.join(foam_blocks)+'\n);\nedges ();\nboundary (\n'
    text+='\n'.join(p+' { type '+('symmetryPlane' if p==PATCH else 'wall')+'; faces ('+' '.join(faces)+'); }' for p,faces in boundaries.items())+'\n);\nmergePatchPairs ();\n'
    data={'cell_centres_m':np.concatenate(centres),'cell_volumes_m3':np.concatenate(volumes),'bounds':np.concatenate(bounds),'base_parent':np.concatenate(parents),'half_parent':np.concatenate(half_parents),'loaded_region':np.concatenate(regions).astype(float)}
    assert len(data['cell_centres_m'])==cells
    return text,data


def initial_average(spec,data):
    """Finite-volume Gaussian mean, analytic in x/z, 16-point Gauss in y."""
    import numpy as np
    b=data['bounds'];s=spec['initial'];centre=s['centre_m'];sigma=s['sigma_m']
    erf=np.vectorize(math.erf,otypes=[float])
    def integral(lo,hi,axis):
        scale=math.sqrt(2)*sigma[axis]
        return sigma[axis]*math.sqrt(math.pi/2)*(erf((hi-centre[axis])/scale)-erf((lo-centre[axis])/scale))
    xint=integral(b[:,0],b[:,1],0)
    nodes,weights=np.polynomial.legendre.leggauss(16)
    ym=(b[:,2]+b[:,3])/2;half=(b[:,3]-b[:,2])/2
    yz=np.zeros(len(b))
    for node,weight in zip(nodes,weights):
        yy=ym+half*node;height=b[:,7]+b[:,8]*(yy-ym)
        z0=b[:,4]+b[:,5]*height;z1=b[:,4]+b[:,6]*height
        yz+=weight*half*np.exp(-.5*((yy-centre[1])/sigma[1])**2)*integral(z0,z1,2)
    return (s['background_mg_m3']+s['gaussian_peak_mg_m3']*xint*yz/data['cell_volumes_m3'])*1e-6


def restrict_to_base(values,volumes,parents):
    import numpy as np
    count=int(parents.max())+1
    weights=np.bincount(parents,weights=volumes,minlength=count)
    if np.any(weights<=0):raise ValueError('Missing parent volume')
    if values.ndim==1:return np.bincount(parents,weights=values*volumes,minlength=count)/weights
    return np.column_stack([restrict_to_base(values[:,i],volumes,parents) for i in range(values.shape[1])])
