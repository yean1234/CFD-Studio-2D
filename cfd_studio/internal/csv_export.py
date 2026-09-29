"""Export a frozen inventory of saved data without running a solver."""
from array import array
from contextlib import contextmanager
import csv
import io
import json
import math
import re
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import threading
import time
import uuid
from urllib.parse import quote
from zipfile import ZipFile, ZIP_DEFLATED

from cfd_studio.result_series import FIELDS, stats, ResultSeries
from types import SimpleNamespace


@contextmanager
def csv_file(archive, name, headers):
    with archive.open(name, 'w', force_zip64=True) as raw:
        with io.TextIOWrapper(raw, encoding='utf-8-sig', newline='') as text:
            writer = csv.writer(text)
            writer.writerow(headers)
            yield writer


def safe_text(value):
    value = str(value)
    return "'"+value if value.startswith(('=', '+', '-', '@', '\t', '\r')) else value


def inventory(root):
    return {str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in root.iterdir() if p.is_file() and (p.suffix in ('.bin', '.npz', '.json'))}


def packed_rows(series, path, config):
    """Keep every stored grid entry, including empty bins and phase masks."""
    raw = path.read_bytes(); prefix = path.name.split('_', 1)[0]
    if prefix == 'bub':
        series.frame_stat(path, 'bubble_count', config, raw=raw)
        return ['cell_index', 'stored_value'], struct.iter_unpack('<If', raw[12:])
    field = next((k for k,v in FIELDS.items() if v[2] == prefix and k not in ('lower_temperature','upper_temperature')), None)
    if field is None:
        raise ValueError('CSV 변환을 지원하지 않는 저장 형식: '+path.name)
    series.frame_stat(path, field, config, raw=raw)  # Validate format before writing.
    nx,ny,nz = struct.unpack_from('<3I', raw, 4); n=nx*ny*nz
    box = struct.unpack_from('<6f', raw, 16)
    phase = prefix == 'phase'
    if not phase:
        values=array('f'); values.frombytes(raw[40:])
        if sys.byteorder!='little': values.byteswap()
    names={'therm':['temperature_K'], 'flow':['ux_m_s','uy_m_s','uz_m_s'],
           'pressure':['kinematic_pressure_m2_s2'], 'turbulence':['k_m2_s2','epsilon_m2_s3'],
           'phase':['water_fraction','vapour_fraction','liquid_fraction','valid_mask'],
           'concentration':['concentration_C_over_Cref'], 'sorbed':['sorbed_Q_over_Cref']}
    def rows():
        for i in range(n):
            ijk=(i%nx,(i//nx)%ny,i//(nx*ny))
            xyz=[box[k]+(ijk[k]+.5)*(box[k+3]-box[k])/d for k,d in enumerate((nx,ny,nz))]
            if phase:
                w,v=raw[40+i],raw[40+n+i]
                data=[w/255,v/255,max(0,255-w-v)/255,raw[40+2*n+i] if raw[:4]==b'PHS2' else '']
            elif prefix=='flow': data=values[i*3:i*3+3]
            elif prefix=='turbulence': data=[values[i],values[n+i]]
            else: data=[values[i]]
            yield [i,*xyz,*data]
    return ['cell_index','x_m','y_m','z_m',*names[prefix]],rows()


def build_csv_archive(series, key, target):
    record, root, config = series.record(key)
    series=ResultSeries(SimpleNamespace(output=series.workspace.output, discover=lambda:{key:record}))
    before=inventory(root); catalog=series.catalog(key)
    if not catalog['metrics']:
        raise ValueError('내보낼 저장 결과가 없습니다.')
    counts={}; axis='iteration' if catalog['axis']=='iteration' else 'time_s'
    with ZipFile(target,'w',compression=ZIP_DEFLATED,compresslevel=1,allowZip64=True) as archive:
        with csv_file(archive,'time_series.csv',[axis,'metric','name','unit','value']) as writer:
            count=0
            if record['kind']=='warehouse':
                from cfd_studio.warehouse_results import WarehouseResults
                reader=WarehouseResults(series.workspace.output,lambda _:root)
                _,model,_,_,times,_,_,_=reader._load(record['rid'])
                for index,t in enumerate(times):
                    frame=reader.frame(record['rid'],index,maximum_points=model['geometry']['cells'])
                    fields={'concentration':frame['concentration']}
                    if 'temperature_field_C' in frame:
                        fields.update(temperature=frame['temperature_field_C'],speed=frame['speed_m_s'],
                                      **{name:[v[j] for v in frame['velocity_m_s']] for j,name in enumerate(('ux','uy','uz'))})
                    for metric in catalog['metrics']:
                        field,stat=metric['id'].split('.')
                        writer.writerow([t,metric['id'],safe_text(metric['name']),metric['unit'],stats(fields[field])[stat]]);count+=1
            else:
                for metric in catalog['metrics']:
                    offset=0
                    while True:
                        page=series.page(key,metric['id'],offset,32)
                        if page['errors']: raise ValueError(metric['name']+': '+page['errors'][0])
                        for x,value in page['points']:
                            writer.writerow([x,metric['id'],safe_text(metric['name']),metric['unit'],value]);count+=1
                        if page['next']>=page['total']: break
                        if page['next']<=offset: raise ValueError('시계열 읽기가 진행되지 않았습니다.')
                        offset=page['next']
            counts['time_series.csv']=count
        if record['kind']=='warehouse':
            for index,t in enumerate(times):
                frame=reader.frame(record['rid'],index,maximum_points=model['geometry']['cells'])
                headers=[axis,'cell_index','x_m','y_m','z_m','concentration_'+frame['concentration_unit']]
                coupled='temperature_field_C' in frame
                if coupled: headers+=['temperature_C','ux_m_s','uy_m_s','uz_m_s','speed_m_s']
                name=f'fields/frame_{index:06d}.csv'
                with csv_file(archive,name,headers) as writer:
                    for i,xyz in enumerate(frame['cell_centres_m']):
                        row=[t,i,*xyz,frame['concentration'][i]]
                        if coupled: row += [frame['temperature_field_C'][i],*frame['velocity_m_s'][i],frame['speed_m_s'][i]]
                        writer.writerow(row)
                counts[name]=len(frame['concentration'])
        else:
            for name in sorted(before):
                if not name.endswith('.bin'): continue
                path=root/name
                try: t=float(path.stem.split('_',1)[1])
                except (ValueError,IndexError): raise ValueError('저장 시점을 확인할 수 없습니다: '+name)
                if not math.isfinite(t): raise ValueError('저장 시점 오류: '+name)
                headers,rows=packed_rows(series,path,config)
                dest='fields/'+path.stem+'.csv'; count=0
                with csv_file(archive,dest,[axis,*headers]) as writer:
                    for row in rows: writer.writerow([t,*row]);count+=1
                counts[dest]=count
        if inventory(root)!=before:
            raise ValueError('내보내는 동안 결과가 변경되었습니다. 저장 완료 후 다시 시도하세요.')
        archive.writestr('manifest.json',json.dumps({'case_id':key,'case_name':record['name'],'axis':catalog['axis'],
            'exported_at':time.time(),'rows':counts,'source_files':before,'config':config,
            'spatial_representation':'saved_solver_cells' if record['kind']=='warehouse' else 'saved_visualization_grid',
            'notes':['전체 저장 시점과 저장 배열을 내보냅니다. 저장되지 않은 원본 셀은 복원하지 않습니다.',
                     '공간 CSV 열 이름에 저장 단위를 표시합니다. 시계열 CSV 단위는 Viewer와 같습니다.',
                     '빈 표시 셀과 상분율 마스크도 보존합니다. 기포 파일은 원본 셀 인덱스와 저장값을 보존합니다.']},ensure_ascii=False,allow_nan=False,indent=2))
    return counts


class CSVExports:
    def __init__(self, series):
        self.series=series;self.lock=threading.Lock();self.files={};self.busy=set()

    def prepare(self,key):
        with self.lock:
            if key in self.busy: raise ValueError('이 Case의 CSV를 이미 생성하고 있습니다.')
            self.busy.add(key)
        folder=None
        try:
            folder=Path(tempfile.mkdtemp(prefix='cfd-studio-csv-'));path=folder/'data.zip'
            name=self.series.record(key)[0]['name']
            filename=re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .')[:90] or 'CFD_Case'
            counts=build_csv_archive(self.series,key,path)
            token=uuid.uuid4().hex
            with self.lock: self.files[token]=(path,filename+'_CSV.zip')
            cleanup=threading.Timer(1800,self.discard,args=(token,));cleanup.daemon=True;cleanup.start()
            return {'token':token,'files':len(counts),'rows':sum(counts.values()),'bytes':path.stat().st_size}
        except BaseException:
            if folder: shutil.rmtree(folder)
            raise
        finally:
            with self.lock:self.busy.discard(key)

    def discard(self,token):
        with self.lock: entry=self.files.pop(token,None)
        if entry: shutil.rmtree(entry[0].parent)

    def download(self,handler,token):
        with self.lock: entry=self.files.pop(token,None)
        if not entry: raise ValueError('다운로드가 만료되었습니다. 전체 CSV를 다시 선택하세요.')
        path,name=entry
        try:
            handler.send_response(200)
            handler.send_header('Content-Type','application/zip')
            handler.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(name))
            handler.send_header('Content-Length',str(path.stat().st_size))
            handler.send_header('Cache-Control','no-store');handler.end_headers()
            with path.open('rb') as source: shutil.copyfileobj(source,handler.wfile,1024*1024)
        finally: shutil.rmtree(path.parent)
