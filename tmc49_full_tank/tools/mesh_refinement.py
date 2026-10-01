"""Box refinement for the conformal tensor-product blockMesh generator.

Refinement is projected onto each coordinate axis to keep shared faces conformal.
Existing grids are unchanged when no refinement regions are supplied.
"""
import math

SCALE={'m':1000.,'cm':10.,'mm':1.}


def refinement_boxes(mesh, bounds):
    regions=mesh.get('refinement_regions',[])
    if not isinstance(regions,list) or len(regions)>64:
        raise ValueError('refinement_regions must contain at most 64 boxes')
    base=mesh.get('dx_mm')
    if type(base) not in (int,float) or not math.isfinite(base) or base<=0:
        raise ValueError('mesh.dx_mm must be positive and finite')
    result=[]
    for r in regions:
        if not isinstance(r,dict) or r.get('shape')!='box' or r.get('unit') not in SCALE:
            raise ValueError('Refinement requires an explicit box and length unit')
        scale=SCALE[r['unit']]
        coords=[]
        for key in ('min','max'):
            v=r.get(key)
            if not isinstance(v,list) or len(v)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) for x in v):
                raise ValueError('Refinement coordinates must contain three finite numbers')
            coords.append([x*scale for x in v])
        lo,hi=coords
        if any(a<0 or b<=a or b>limit for a,b,limit in zip(lo,hi,bounds)):
            raise ValueError('Refinement box is outside the calculation domain')
        q=r.get('cell_size',{})
        value=q.get('value') if isinstance(q,dict) else None
        if type(value) not in (int,float) or not math.isfinite(value) or q.get('unit') not in SCALE:
            raise ValueError('Refinement cell size needs a finite value and unit')
        size=value*SCALE[q['unit']]
        if not 0<size<base:raise ValueError('Refinement cell size must be smaller than the base size')
        result.append((lo,hi,size))
    return result


def refined_axis(points,axis,base,boxes):
    """Return block boundaries and shared cell counts, in millimetres."""
    if not boxes:return points,[max(2,round((b-a)/base)) for a,b in zip(points,points[1:])]
    cuts=sorted(set(points+[p[axis] for lo,hi,_ in boxes for p in (lo,hi)]))
    counts=[]
    for a,b in zip(cuts,cuts[1:]):
        local=min([base]+[size for lo,hi,size in boxes if a<hi[axis] and b>lo[axis]])
        counts.append(max(2,math.ceil((b-a)/local)))
    return cuts,counts


def validate_legacy_fills(config):
    """Do not silently ignore conflicting fill metadata in a CLI-built case."""
    tank=config['tank'];boundary=config['layers']['dielectric_mm'];height=tank['liquid_height_mm']
    for key,start,end in [('dielectric_fluid',0,boundary),('water',boundary,height)]:
        part=config.get(key,{})
        if 'fill' not in part:continue
        f=part['fill'];scale=SCALE.get(f.get('unit')) if isinstance(f,dict) else None
        if not scale or f.get('container_path')!=['tank'] or f.get('axis')!='y' or tank.get('interior') or any(type(f.get(k)) not in (int,float) or not math.isfinite(f[k]) for k in ('start','end')) or not math.isclose(f['start']*scale,start) or not math.isclose(f['end']*scale,end):
            raise ValueError('Fill definition does not match the two-layer runner geometry')
