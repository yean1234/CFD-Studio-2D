"""Read-only, paged chart data. No solver execution or rewritten result fields."""
from array import array
from collections import OrderedDict
import json
import math
from pathlib import Path
import struct
import sys
import threading
from zipfile import BadZipFile

FIELDS = {
 'lower_temperature': ('유전체층 온도', '°C', 'therm', b'THM1', 1),
 'upper_temperature': ('상단 액체 온도', '°C', 'therm', b'THM1', 1),
 'temperature': ('온도', '°C', 'therm', b'THM1', 1),
 'speed': ('유속', 'm/s', 'flow', b'FLW1', 3),
 'ux': ('X 유속', 'm/s', 'flow', b'FLW1', 3),
 'uy': ('Y 유속', 'm/s', 'flow', b'FLW1', 3),
 'uz': ('Z 유속', 'm/s', 'flow', b'FLW1', 3),
 'pressure': ('압력', 'm²/s²', 'pressure', b'PRS1', 1),
 'k': ('난류 운동에너지', 'm²/s²', 'turbulence', b'TRB1', 2),
 'epsilon': ('난류 소산율', 'm²/s³', 'turbulence', b'TRB1', 2),
 'water': ('물 상분율', '1', 'phase', b'PHS2', 3),
 'vapour': ('증기 상분율', '1', 'phase', b'PHS2', 3),
 'liquid': ('유전체 상분율', '1', 'phase', b'PHS2', 3),
 'concentration': ('농도', 'C/C_ref', 'concentration', b'CON1', 1),
 'sorbed': ('흡착량', 'Q/C_ref', 'sorbed', b'SOR1', 1),
}
STATS = {'mean': '평균', 'min': '최솟값', 'max': '최댓값'}
HISTORY = {**{f'probe{i+1}': (f'T{i+1} 온도', '°C', 'probes', i+1) for i in range(4)},
           't5': ('T5 입구 온도 (입력)', '°C', 'coil', 1), 't6': ('T6 출구 온도 (계산)', '°C', 'coil', 1),
           'coil': ('코일 평균 온도', '°C', 'coil', 1), 'volume': ('기포 부피', 'mL', 'vapor', 1)}


def output_definitions(model):
    keys = {'warehouse': ['concentration','temperature','speed','ux','uy','uz'],
            'immersion': ['temperature','lower_temperature','upper_temperature','speed','ux','uy','uz','water','vapour','liquid'],
            'grain_silo': ['speed','ux','uy','uz','pressure','k','epsilon']}.get(model, [])
    return [{'id': k, 'name': FIELDS[k][0], 'unit': 'mg/m³' if k == 'concentration' else 'Pa' if k == 'pressure' else FIELDS[k][1], 'statistics': list(STATS.values())} for k in keys] + (
        [{'id': k, 'name': v[0], 'unit': v[1], 'statistics': []} for k,v in HISTORY.items()] + [{'id':'bubble_count','name':'기포 셀 수','unit':'개','statistics':[]}] if model == 'immersion' else [])


def read(path, default):
    try: return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except FileNotFoundError: return default


def stats(values):
    if not values: return {k: None for k in STATS}
    if not all(math.isfinite(v) for v in values): raise ValueError('유한하지 않은 저장값')
    return {'min': min(values), 'mean': math.fsum(v/len(values) for v in values), 'max': max(values)}


class ResultSeries:
    def __init__(self, workspace):
        self.workspace = workspace
        self.cache = OrderedDict()
        self.catalog_cache = OrderedDict()
        self.index_cache = OrderedDict()
        self.lock = threading.Lock()

    def record(self, key):
        record = self.workspace.discover().get(key)
        if not record or not record.get('path'): raise ValueError('저장된 결과가 없습니다')
        root = Path(record['path'])
        config = read(root/('transport_input.json' if record['kind']=='warehouse' else 'case_config.json'), {})
        if not config: config = read(root/'config.json', {})
        return record, root, config

    def catalog(self, key):
        record, root, config = self.record(key)
        stamps=tuple((p.stat().st_mtime_ns,p.stat().st_size) if p.exists() else None for p in (root,root/'case_config.json',root/'transport_input.json',root/'history.json',root/'model_contract.json'))
        bin_names=tuple(sorted(p.name for p in root.glob('*.bin'))) if record['kind']!='warehouse' else ()
        cache_key=(key,str(root),stamps,bin_names)
        with self.lock:
            if cache_key in self.catalog_cache: return self.catalog_cache[cache_key]
        axis = 'iteration' if config.get('openfoam_mapping',{}).get('solver')=='simpleFoam' else 'time'
        fields, metrics = [], []
        if record['kind']=='warehouse':
            model = read(root/'model_contract.json', {})
            fields = ['concentration'] + (['temperature','speed','ux','uy','uz'] if model.get('kind')=='clo2_coupled_scenario' else [])
        else:
            prefixes = {name.split('_',1)[0] for name in bin_names}
            fields = [k for k,v in FIELDS.items() if v[2] in prefixes]
            if not config.get('layers',{}).get('dielectric_mm'): fields=[k for k in fields if k not in ('lower_temperature','upper_temperature')]
            hist = read(root/'history.json', {})
            for k,(name,unit,group,column) in HISTORY.items():
                if k in ('t5','t6') and self.coil_factor(config,k) is None: continue
                if hist.get(group): metrics.append({'id':k,'name':name,'unit':unit})
            if 'bub' in prefixes: metrics.append({'id':'bubble_count','name':'기포 셀 수','unit':'개'})
        for k in fields:
            name,unit,*_ = FIELDS[k]
            if k=='concentration' and record['kind']=='warehouse' and model.get('kind')!='normalized_gable_verification': unit='mg/m³'
            if k=='pressure' and config.get('published',{}).get('rho_kg_m3'): unit='Pa'
            metrics += [{'id': k+'.'+stat,'name':name+' · '+label,'unit':unit} for stat,label in STATS.items()]
        result={'id':key,'name':record['name'],'axis':axis,'metrics':metrics}
        with self.lock:
            self.catalog_cache[cache_key]=result
            while len(self.catalog_cache)>32: self.catalog_cache.popitem(last=False)
        return result

    def frame_stat(self, path, field, config):
        stamp=path.stat(); cache_key=(str(path),stamp.st_mtime_ns,stamp.st_size,field,config.get('published',{}).get('rho_kg_m3'),config.get('layers',{}).get('dielectric_mm'))
        with self.lock:
            if cache_key in self.cache: self.cache.move_to_end(cache_key); return self.cache[cache_key]
        raw=path.read_bytes()
        if field=='bubble_count':
            if len(raw)<12 or raw[:4]!=b'BUB1': raise ValueError('기포 파일 형식 오류')
            n,total=struct.unpack_from('<2I',raw,4)
            if not total or n>total or len(raw)!=12+n*8: raise ValueError('기포 파일 길이 오류')
            for i,v in struct.iter_unpack('<If',raw[12:]):
                if i>=total or not math.isfinite(v): raise ValueError('기포 저장값 오류')
            return {'value':n}
        _,_,_,magic,channels=FIELDS[field]
        if len(raw)<40: raise ValueError('결과 머리말 길이 오류')
        nx,ny,nz=struct.unpack_from('<3I',raw,4); n=nx*ny*nz
        bbox=struct.unpack_from('<6f',raw,16)
        if not n or any(not math.isfinite(v) for v in bbox) or any(bbox[i]>=bbox[i+3] for i in range(3)): raise ValueError('격자 범위 오류')
        phase=field in ('water','vapour','liquid')
        if phase:
            if raw[:4] not in (b'PHS1',b'PHS2'): raise ValueError('상분율 형식 오류')
            channels=3 if raw[:4]==b'PHS2' else 2
            if len(raw)!=40+n*channels: raise ValueError('상분율 크기 오류')
            w,v=raw[40:40+n],raw[40+n:40+2*n]
            mask=raw[40+2*n:] if channels==3 else None
            values=[(w[i] if field=='water' else v[i] if field=='vapour' else max(0,255-w[i]-v[i]))/255 for i in range(n) if mask is None or mask[i]]
        else:
            if raw[:4]!=magic or len(raw)!=40+n*channels*4: raise ValueError('결과 형식·크기 오류')
            values=array('f'); values.frombytes(raw[40:])
            if sys.byteorder!='little': values.byteswap()
            if not all(math.isfinite(v) for v in values): raise ValueError('유한하지 않은 저장값')
            if field in ('speed','ux','uy','uz','pressure','k','epsilon'):
                plane=nx*ny;keep=[]
                for z in range(nz):
                    if channels==3: occupied=any(abs(v)>1e-30 for v in values[z*plane*3:(z+1)*plane*3])
                    else: occupied=any(abs(values[c*n+i])>1e-30 for c in range(channels) for i in range(z*plane,(z+1)*plane))
                    if occupied: keep.append(z)
                missing=nz-len(keep)
                if len(keep)>=2 and missing>=3 and missing>=nz*.05 and any(b>a+1 for a,b in zip(keep,keep[1:])):
                    values=[values[i] for z in keep for i in range(z*plane*3,(z+1)*plane*3)] if channels==3 else [values[c*n+i] for c in range(channels) for z in keep for i in range(z*plane,(z+1)*plane)]
                    n=plane*len(keep)
            if field=='speed': values=[math.hypot(*values[i:i+3]) for i in range(0,len(values),3)]
            elif field in ('ux','uy','uz'): values=values[['ux','uy','uz'].index(field)::3]
            elif field in ('k','epsilon'): values=values[:n] if field=='k' else values[n:]
            elif field in ('lower_temperature','upper_temperature'):
                height=config['layers']['dielectric_mm']/1000
                values=[v-273.15 for i,v in enumerate(values) if v>0 and ((bbox[1]+((i//nx)%ny+.5)*(bbox[4]-bbox[1])/ny<height)==(field=='lower_temperature'))]
            elif field=='temperature': values=[v-273.15 for v in values if v>0]  # zero denotes an empty display bin
            elif field=='pressure':
                rho=config.get('published',{}).get('rho_kg_m3',1)
                if not isinstance(rho,(int,float)) or not math.isfinite(rho) or rho<=0: raise ValueError('압력 밀도 오류')
                values=[v*rho for v in values]
        result=stats(values)
        with self.lock:
            self.cache[cache_key]=result
            while len(self.cache)>4096: self.cache.popitem(last=False)
        return result

    def page(self, key, metric, offset=0, limit=16):
        if not 0<=offset or not 1<=limit<=32: raise ValueError('조회 범위 오류')
        catalog=self.catalog(key)
        if metric not in {m['id'] for m in catalog['metrics']}: raise ValueError('저장되지 않은 결과 항목입니다')
        record,root,config=self.record(key)
        points=[]; errors=[]
        if record['kind']=='warehouse':
            from cfd_studio.warehouse_results import WarehouseResults
            reader=WarehouseResults(self.workspace.output,lambda _:root)
            _,model,_,_,times,_,_,_=reader._load(record['rid'])
            field,stat=metric.split('.'); total=len(times)
            for index in range(offset,min(total,offset+limit)):
                try:
                    frame=reader.frame(record['rid'],index,maximum_points=model['geometry']['cells'])
                    values=frame['concentration'] if field=='concentration' else frame['temperature_field_C'] if field=='temperature' else frame['speed_m_s'] if field=='speed' else [v[['ux','uy','uz'].index(field)] for v in frame['velocity_m_s']]
                    points.append([times[index],stats(values)[stat]])
                except (ValueError,OSError,KeyError,BadZipFile,EOFError,struct.error) as error: points.append([times[index],None]);errors.append(str(error))
            basis='저장 원본장 대조 · 셀 산술 통계'
        elif metric in HISTORY:
            _,_,group,col=HISTORY[metric]; rows=read(root/'history.json',{}).get(group,[])
            merged={}
            for row in rows:
                if not isinstance(row,list) or len(row)<=col or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (row[0],row[col])): raise ValueError('계측 이력 형식 오류')
                value=row[col]
                if metric in ('t5','t6'):
                    inlet,factor=self.coil_factor(config,metric)
                    value=inlet if metric=='t5' else inlet+factor*(value-inlet)
                merged[row[0]]=value
            ordered=sorted(merged.items());total=len(ordered);points=ordered[offset:offset+limit];basis='저장된 계측 이력' if metric not in ('t5','t6') else 'Case의 입구 온도 입력' if metric=='t5' else 'Case의 코일 이력·유량·전열계수로 계산한 출구 온도'
        else:
            field,stat=(metric.split('.') if '.' in metric else (metric,'value'))
            prefix='bub' if field=='bubble_count' else FIELDS[field][2]
            index_key=(str(root),tuple(sorted(p.name for p in root.glob(prefix+'_*.bin'))))
            with self.lock: files=self.index_cache.get(index_key)
            if files is None: files=self.index_files(root,prefix,index_key)
            total=len(files)
            for t,path in files[offset:offset+limit]:
                try: points.append([t,self.frame_stat(path,field,config)[stat]])
                except (ValueError,OSError,struct.error) as error: points.append([t,None]); errors.append(path.name+': '+str(error))
            basis='저장 시각화 격자 · 빈 온도 셀 제외 · 상분율 마스크·구형 빈 평면 보정 적용'
        return {'id':key,'metric':metric,'axis':catalog['axis'],'points':points,'total':total,'next':min(total,offset+limit),'errors':errors,'basis':basis}

    @staticmethod
    def coil_factor(config,metric):
        k=config.get('coil',{})
        try:
            inlet=float(k['Ta_C'])
            if not math.isfinite(inlet): return None
            if metric=='t5': return inlet,0
            flow=float(k['flow_LPM'])
            lengths=[(float(k[a+'1'])-float(k[a+'0']))/1000 for a in 'xyz']
            if flow<=0 or not all(v>0 for v in lengths): return None
            x,y,z=lengths;factor=float(k['h_W_m2K'])*2*(x*y+y*z+z*x)/(flow/60*4178)
            return (inlet,factor) if math.isfinite(factor) and factor>=0 else None
        except (KeyError,TypeError,ValueError): return None

    def index_files(self,root,prefix,index_key):
        files=[]
        for path in root.glob(prefix+'_*.bin'):
            try: t=float(path.stem[len(prefix)+1:])
            except ValueError: continue
            if math.isfinite(t): files.append((t,path))
        files.sort()
        if len({t for t,_ in files})!=len(files): raise ValueError('같은 X의 결과 파일이 중복되어 있습니다')
        with self.lock:
            self.index_cache[index_key]=files
            while len(self.index_cache)>32: self.index_cache.popitem(last=False)
        return files
