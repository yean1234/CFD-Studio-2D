"""Box refinement for the conformal tensor-product blockMesh generator.

Refinement is projected onto each coordinate axis to keep shared faces conformal.
Existing grids are unchanged when no refinement regions are supplied.
"""
import math

SCALE={'m':1000.,'cm':10.,'mm':1.}


def geometry_box(config, path):
    """Resolve an exact Config path to current axis-aligned bounds, without caching."""
    if not isinstance(path, list) or not path or len(path)>20:
        raise ValueError('[MESH-R001] Invalid refinement target_path')
    part=config
    for key in path:
        if type(key) not in (str,int) or key in ('__proto__','constructor','prototype'):
            raise ValueError('[MESH-R001] Invalid refinement target_path')
        try:
            if isinstance(part,list) and (type(key) is not int or key<0):raise KeyError(key)
            part=part[key]
        except (KeyError,IndexError,TypeError):
            raise ValueError('[MESH-R001] Refinement target no longer exists') from None
    if not isinstance(part,dict):raise ValueError('[MESH-R001] Refinement target must be a geometry object')
    shape=part.get('shape')
    if not shape:
        if path==['tank']:
            part={'unit':'mm','min':[0,0,0],'max':[part.get(k) for k in ('width_mm','liquid_height_mm','depth_mm')]}
        elif path in (['board'],['coil']):
            part={'unit':'mm','min':[part.get(k+'0') for k in 'xyz'],'max':[part.get(k+'1') for k in 'xyz']}
        elif path in (['dielectric_fluid'],['water']) and 'tank' in config and 'layers' in config:
            tank=config['tank'];boundary=config['layers']['dielectric_mm']
            part={'unit':'mm','min':[0,boundary if path==['water'] else 0,0],
                  'max':[tank['width_mm'],tank['liquid_height_mm'] if path==['water'] else boundary,tank['depth_mm']]}
        elif 'min_m' in part and 'max_m' in part:
            part={'unit':'m','min':part['min_m'],'max':part['max_m']}
        else:raise ValueError('[MESH-R002] Target has no supported explicit primitive')
        shape='box'
    if shape=='box':return {'shape':'box','unit':part.get('unit'),'min':part.get('min'),'max':part.get('max')}
    if shape not in ('sphere','cylinder'):raise ValueError('[MESH-R002] Target shape is unsupported')
    center=part.get('center');radius=part.get('radius')
    if not isinstance(center,list) or len(center)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in center) or type(radius) not in (int,float) or not math.isfinite(radius) or radius<=0:
        raise ValueError('[MESH-R002] Invalid target dimensions')
    extents=[radius]*3
    if shape=='cylinder':
        axis=part.get('axis');height=part.get('height')
        if axis not in ('x','y','z') or type(height) not in (int,float) or not math.isfinite(height) or height<=0:
            raise ValueError('[MESH-R002] Invalid cylinder axis or height')
        extents['xyz'.index(axis)]=height/2
    return {'shape':'box','unit':part.get('unit'),'min':[v-e for v,e in zip(center,extents)],'max':[v+e for v,e in zip(center,extents)]}


def refinement_boxes(mesh, bounds, config=None, origin=None):
    regions=mesh.get('refinement_regions',[])
    if not isinstance(regions,list) or len(regions)>64:
        raise ValueError('refinement_regions must contain at most 64 boxes')
    base=mesh.get('dx_mm')
    if type(base) not in (int,float) or not math.isfinite(base) or base<=0:
        raise ValueError('mesh.dx_mm must be positive and finite')
    origin=[0,0,0] if origin is None else origin
    result=[]
    for r in regions:
        if isinstance(r,dict) and 'target_path' in r:
            if any(k in r for k in ('shape','unit','min','max')):
                raise ValueError('[MESH-R003] Use a geometry target or explicit bounds, not both')
            r={**r,**geometry_box(config or {},r['target_path'])}
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
        if any(a<start or b<=a or b>limit for a,b,start,limit in zip(lo,hi,origin,bounds)):
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
