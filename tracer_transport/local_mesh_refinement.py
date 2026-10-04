"""Local box spacing for the warehouse's existing aligned blocks.

Existing block boundaries and restriction-parent ordering are retained. A box
refines every aligned interval it intersects, projected on the three axes.
"""
import math


def refine_counts(spec,x,y,z,xc,yc,zc):
    from tmc49_full_tank.tools.mesh_refinement import collect_refinements
    mesh=spec['porous_mesh'];regions=collect_refinements(spec,mesh)
    if not regions:return xc,yc,zc
    from tmc49_full_tank.tools.mesh_refinement import refinement_boxes
    g=spec['geometry_spec']['geometry'];base=min(mesh['base_max_spacing_m'])
    boxes=refinement_boxes({'dx_mm':base*1000,'refinement_regions':mesh.get('refinement_regions',[])},[g['length_m']*1000,g['width_m']*1000,(g['eaves_m']+g['roof_rise_m'])*1000],spec)
    boxes=[([v*.001 for v in lo],[v*.001 for v in hi],size*.001) for lo,hi,size in boxes]
    def roof(yy):return g['eaves_m']+g['roof_rise_m']*(1-abs(2*yy/g['width_m']-1))
    for lo,hi,_ in boxes:
        if hi[2]>min(roof(lo[1]),roof(hi[1]))+1e-10:raise ValueError('Local refinement box exceeds the roof')
    factors=[1,math.hypot(1,2*g['roof_rise_m']/g['width_m']),1]
    result=[]
    for axis,(points,counts) in enumerate(zip([x,y,z+[g['eaves_m']+g['roof_rise_m']]],[xc,yc,zc])):
        values=[]
        for a,b,count in zip(points,points[1:],counts):
            sizes=[size for lo,hi,size in boxes if a<hi[axis] and b>lo[axis]]
            values.append(max(int(count),math.ceil((b-a)*factors[axis]/min(sizes))) if sizes else int(count))
        result.append(values)
    return tuple(result)
