"""Cell-containing spatial sampling and linear temporal interpolation; no extrapolation."""
from pathlib import Path
import numpy as np


class ConcentrationField:
    def __init__(self, path):
        with np.load(Path(path), allow_pickle=False) as data:
            self.times=data['times'].copy()
            self.c=data['concentration'].copy()
            self.regions=data['region_id'].copy()
            self.shape=data['shape_xyz'].copy()
            self.lengths=data['lengths_m'].copy()
        if (self.shape.shape!=(3,) or self.lengths.shape!=(3,)
                or not np.isfinite(self.shape).all() or np.any(self.shape<1)
                or not np.all(self.shape==np.floor(self.shape))
                or not np.isfinite(self.lengths).all() or np.any(self.lengths<=0)
                or self.times.ndim!=1 or len(self.times)<1 or not np.isfinite(self.times).all()
                or self.c.shape!=(len(self.times),int(np.prod(self.shape)))
                or self.regions.shape!=(int(np.prod(self.shape)),)
                or not (np.issubdtype(self.regions.dtype,np.integer)
                        or np.issubdtype(self.regions.dtype,np.floating))
                or not np.isfinite(self.regions).all()
                or not np.all(self.regions==np.floor(self.regions))
                or not np.isfinite(self.c).all() or not np.all(np.diff(self.times)>0)):
            raise ValueError('Invalid concentration series')

    def sample_concentration(self, position_xyz_m, time_s, region_id=None):
        try:
            p=np.asarray(position_xyz_m,dtype=float)
            time_s=float(time_s)
        except (ValueError,TypeError):
            return {'valid':False,'reason':'invalid_input','concentration':None}
        if p.shape!=(3,) or not np.isfinite(p).all() or not np.isfinite(time_s):
            return {'valid':False,'reason':'invalid_input','concentration':None}
        if np.any(p<0) or np.any(p>=self.lengths):
            return {'valid':False,'reason':'outside_domain','concentration':None}
        if time_s<self.times[0] or time_s>self.times[-1]:
            return {'valid':False,'reason':'outside_time','concentration':None}
        i,j,k=np.floor(p/self.lengths*self.shape).astype(int)
        cell=int(i+self.shape[0]*(j+self.shape[1]*k))
        reg=int(self.regions[cell])
        if reg<0 or (region_id is not None and reg!=region_id):
            return {'valid':False,'reason':'region_mismatch_or_solid','concentration':None}
        value=float(np.interp(time_s,self.times,self.c[:,cell]))
        return {'valid':True,'concentration':value,'unit':'C/C_ref','region_id':reg,
                'cell_id':cell,'spatial_method':'containing_cell','temporal_method':'linear'}
