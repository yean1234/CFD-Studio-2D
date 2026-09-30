"""Host telemetry with explicit metric sources and per-sample timestamps.

No shell is used for CPU/RAM or NVML. Unsupported readings remain None.
GPU activity uses the busiest Windows engine; NVML supplies separate VRAM data.
"""
import atexit
import csv
import ctypes
import io
import math
import os
import subprocess
import time


def numeric(value):
    try:
        result=float(value)
        return result if math.isfinite(result) and result>=0 else None
    except (TypeError,ValueError):return None


def parse_smi(text,sampled_at):
    result=[]
    for row in csv.reader(io.StringIO(text)):
        if len(row)<6:continue
        index=numeric(row[0])
        if index is None or not index.is_integer():continue
        result.append({'i':int(index),'name':row[1].strip(),'id':row[2].strip(),
                       'u':numeric(row[3]),'mu':numeric(row[4]),'mt':numeric(row[5]),
                       'sampled_at':sampled_at,'source':'nvidia-smi'})
    return result


class HostCPU:
    def __init__(self):
        if os.name!='nt':raise OSError('Windows host required')
        from ctypes import wintypes as w
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.filetime=w.FILETIME
        self.kernel.GetSystemTimes.argtypes=[ctypes.POINTER(w.FILETIME)]*3
        self.kernel.GetSystemTimes.restype=w.BOOL
        class Memory(ctypes.Structure):
            _fields_=[('length',w.DWORD),('load',w.DWORD)]+[(n,ctypes.c_ulonglong) for n in ('total','free','page_total','page_free','virtual_total','virtual_free','extended')]
        self.Memory=Memory
        self.kernel.GlobalMemoryStatusEx.argtypes=[ctypes.POINTER(Memory)]
        self.kernel.GlobalMemoryStatusEx.restype=w.BOOL
        self.previous=None

    def sample(self):
        idle,kernel,user=(self.filetime() for _ in range(3))
        if not self.kernel.GetSystemTimes(ctypes.byref(idle),ctypes.byref(kernel),ctypes.byref(user)):raise ctypes.WinError(ctypes.get_last_error())
        ticks=lambda t:(t.dwHighDateTime<<32)|t.dwLowDateTime
        total=ticks(kernel)+ticks(user);current=(ticks(idle),total);now=time.time();usage=None
        if self.previous:
            delta=total-self.previous[1];unused=current[0]-self.previous[0]
            if delta>0 and 0<=unused<=delta:usage=round(100*(delta-unused)/delta,1)
        self.previous=current
        result={'cpu':usage,'cpu_sampled_at':now,'cpu_source':'GetSystemTimes','logical':os.cpu_count()}
        memory=self.Memory();memory.length=ctypes.sizeof(memory)
        if self.kernel.GlobalMemoryStatusEx(ctypes.byref(memory)):
            result.update(ram_u=(memory.total-memory.free)//1048576,ram_t=memory.total//1048576)
        return result


class Nvidia:
    class Util(ctypes.Structure):_fields_=[('gpu',ctypes.c_uint),('memory',ctypes.c_uint)]
    class Memory(ctypes.Structure):_fields_=[('total',ctypes.c_ulonglong),('free',ctypes.c_ulonglong),('used',ctypes.c_ulonglong)]

    def __init__(self):
        if os.name!='nt':raise OSError('Windows host required')
        self.dll=ctypes.WinDLL('nvml.dll')
        self.bind('nvmlInit_v2',[]);self.bind('nvmlShutdown',[])
        self.bind('nvmlDeviceGetCount_v2',[ctypes.POINTER(ctypes.c_uint)])
        self.bind('nvmlDeviceGetHandleByIndex_v2',[ctypes.c_uint,ctypes.POINTER(ctypes.c_void_p)])
        self.bind('nvmlDeviceGetName',[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_uint])
        self.bind('nvmlDeviceGetUUID',[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_uint])
        self.bind('nvmlDeviceGetUtilizationRates',[ctypes.c_void_p,ctypes.POINTER(self.Util)])
        self.bind('nvmlDeviceGetMemoryInfo',[ctypes.c_void_p,ctypes.POINTER(self.Memory)])
        self.check(self.dll.nvmlInit_v2());self.initialized=True;atexit.register(self.close)

    def close(self):
        if self.initialized:self.dll.nvmlShutdown();self.initialized=False

    def bind(self,name,args):
        f=getattr(self.dll,name);f.argtypes=args;f.restype=ctypes.c_int

    @staticmethod
    def check(code):
        if code:raise OSError('NVML status '+str(code))

    def sample(self):
        count=ctypes.c_uint();self.check(self.dll.nvmlDeviceGetCount_v2(ctypes.byref(count)));result=[]
        for i in range(count.value):
            handle=ctypes.c_void_p();self.check(self.dll.nvmlDeviceGetHandleByIndex_v2(i,ctypes.byref(handle)))
            name=ctypes.create_string_buffer(128);uuid=ctypes.create_string_buffer(128)
            self.dll.nvmlDeviceGetName(handle,name,len(name));self.dll.nvmlDeviceGetUUID(handle,uuid,len(uuid))
            util=self.Util();memory=self.Memory()
            uc=self.dll.nvmlDeviceGetUtilizationRates(handle,ctypes.byref(util));mc=self.dll.nvmlDeviceGetMemoryInfo(handle,ctypes.byref(memory))
            result.append({'i':i,'id':uuid.value.decode(errors='replace') or str(i),'name':name.value.decode(errors='replace'),
                           'u':util.gpu if uc==0 else None,'mu':memory.used/1048576 if mc==0 else None,
                           'mt':memory.total/1048576 if mc==0 else None,'source':'NVML','sampled_at':time.time()})
        return result


class Monitor:
    def __init__(self,smi=None,drives=None):
        self.smi=smi;self.drives=drives;self.cpu=None;self.nvidia=None;self.retry_nvml=0
        self.last_gpus=[];self.engines=None;self.luids={};self.retry_engines=0;self.refresh_luids=0

    def sample(self):
        start=time.perf_counter();result={};errors=[]
        try:
            if self.cpu is None:self.cpu=HostCPU()
            result.update(self.cpu.sample())
        except Exception as error:errors.append('cpu:'+type(error).__name__)
        try:
            if self.nvidia is None and time.monotonic()>=self.retry_nvml:
                self.retry_nvml=time.monotonic()+60
                try:self.nvidia=Nvidia()
                except (OSError,AttributeError):pass
            if self.nvidia is not None:gpus=self.nvidia.sample()
            elif self.smi:
                run=subprocess.run([self.smi,'--query-gpu=index,name,uuid,utilization.gpu,memory.used,memory.total','--format=csv,noheader,nounits'],capture_output=True,timeout=2,creationflags=0x08000000 if os.name=='nt' else 0,check=True)
                gpus=parse_smi(run.stdout.decode(errors='replace'),time.time())
            else:raise OSError('GPU telemetry unavailable')
            try:
                from cfd_studio.windows_gpu import EngineCounters,cuda_luids
                if time.monotonic()>=self.refresh_luids:
                    self.refresh_luids=time.monotonic()+60;self.luids=cuda_luids()
                if self.engines is None and time.monotonic()>=self.retry_engines:
                    self.retry_engines=time.monotonic()+60;self.engines=EngineCounters()
                engine_values=self.engines.sample() if self.engines else {}
            except Exception as error:
                engine_values={};errors.append('gpu_engines:'+type(error).__name__)
                if self.engines:self.engines.close();self.engines=None
                self.retry_engines=time.monotonic()+5
            for gpu in gpus:
                engine=engine_values.get(self.luids.get(gpu['id']),{})
                gpu.update(driver_u=gpu['u'],u=engine.get('u'),engine=engine.get('engine'),memory_source=gpu['source'],source='Windows GPU Engine')
            self.last_gpus=gpus;result['gpus']=gpus
        except Exception as error:
            errors.append('gpu:'+type(error).__name__)
            if self.nvidia:self.nvidia.close();self.nvidia=None
            # Preserve device identity, never turn failed readings into zero or fresh data.
            result['gpus']=[{**g,'u':None,'mu':None,'mt':None,'stale':True} for g in self.last_gpus]
        try:result['drives']=self.drives() if self.drives else []
        except Exception as error:errors.append('drives:'+type(error).__name__)
        result.update(sampled_at=time.time(),collection_ms=round((time.perf_counter()-start)*1000,1))
        result['ok']=result.get('cpu') is not None or any(g.get('u') is not None for g in result.get('gpus',[]))
        result['stale']=not result['ok']
        if errors:result['_errors']=errors
        return result
