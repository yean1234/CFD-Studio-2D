"""Windows GPU Engine counters, grouped per physical engine before taking the maximum.

Sources: Microsoft PDH API and CUDA Driver API cuDeviceGetLuid/cuDeviceGetUuid.
No CUDA context, workload, or device configuration is created or changed.
"""
import atexit
import ctypes
import math
import os
import re
import uuid

INSTANCE=re.compile(r'luid_0x([0-9a-f]+)_0x([0-9a-f]+)_phys_(\d+)_eng_(\d+)_engtype_(.*)',re.I)


def aggregate_engines(samples):
    engines={}
    for name,value,status in samples:
        match=INSTANCE.search(name)
        if not match or status not in (0,1) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:continue
        hi,low,physical,engine,kind=match.groups()
        key=(int(hi,16),int(low,16),int(physical),int(engine))
        row=engines.setdefault(key,{'u':0.0,'engine':kind});row['u']+=value
    result={}
    for (hi,low,physical,_),row in engines.items():
        row={**row,'u':min(100.0,row['u']),'physical':physical}
        if row['u']>=result.get((hi,low),{}).get('u',-1):result[(hi,low)]=row
    return result


def cuda_luids():
    if os.name!='nt':raise OSError('Windows host required')
    lib=ctypes.WinDLL('nvcuda.dll')
    signatures={'cuInit':[ctypes.c_uint],'cuDeviceGetCount':[ctypes.POINTER(ctypes.c_int)],'cuDeviceGet':[ctypes.POINTER(ctypes.c_int),ctypes.c_int],
                'cuDeviceGetUuid':[ctypes.c_void_p,ctypes.c_int],'cuDeviceGetLuid':[ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint),ctypes.c_int]}
    for name,args in signatures.items():f=getattr(lib,name);f.argtypes=args;f.restype=ctypes.c_int
    if lib.cuInit(0):raise OSError('CUDA device enumeration unavailable')
    count=ctypes.c_int()
    if lib.cuDeviceGetCount(ctypes.byref(count)):raise OSError('CUDA device count unavailable')
    result={}
    for index in range(count.value):
        device=ctypes.c_int();identity=ctypes.create_string_buffer(16);luid=ctypes.create_string_buffer(8);mask=ctypes.c_uint()
        if lib.cuDeviceGet(ctypes.byref(device),index) or lib.cuDeviceGetUuid(identity,device) or lib.cuDeviceGetLuid(luid,ctypes.byref(mask),device):continue
        result['GPU-'+str(uuid.UUID(bytes=identity.raw))]=(int.from_bytes(luid.raw[4:8],'little'),int.from_bytes(luid.raw[:4],'little'))
    return result


class EngineCounters:
    def __init__(self):
        if os.name!='nt':raise OSError('Windows host required')
        self.dll=ctypes.WinDLL('pdh');self.query=ctypes.c_void_p();self.counter=ctypes.c_void_p()
        self.bind('PdhOpenQueryW',[ctypes.c_wchar_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_void_p)])
        self.bind('PdhAddEnglishCounterW',[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_void_p)])
        self.bind('PdhCollectQueryData',[ctypes.c_void_p]);self.bind('PdhCloseQuery',[ctypes.c_void_p])
        self.bind('PdhGetFormattedCounterArrayW',[ctypes.c_void_p,ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32),ctypes.POINTER(ctypes.c_uint32),ctypes.c_void_p])
        self.check(self.dll.PdhOpenQueryW(None,0,ctypes.byref(self.query)))
        try:
            self.check(self.dll.PdhAddEnglishCounterW(self.query,r'\GPU Engine(*)\Utilization Percentage',0,ctypes.byref(self.counter)))
            self.check(self.dll.PdhCollectQueryData(self.query))
        except Exception:self.close();raise
        self.ready=False;atexit.register(self.close)

    def bind(self,name,args):f=getattr(self.dll,name);f.argtypes=args;f.restype=ctypes.c_uint32
    @staticmethod
    def check(code):
        if code:raise OSError('PDH status '+hex(code))
    def close(self):
        if self.query.value:self.dll.PdhCloseQuery(self.query);self.query=ctypes.c_void_p()

    def sample(self):
        if not self.ready:self.ready=True;return {}
        self.check(self.dll.PdhCollectQueryData(self.query))
        class Value(ctypes.Structure):_fields_=[('status',ctypes.c_uint32),('value',ctypes.c_double)]
        class Item(ctypes.Structure):_fields_=[('name',ctypes.c_wchar_p),('formatted',Value)]
        size=ctypes.c_uint32();count=ctypes.c_uint32();flags=0x200|0x8000
        for _ in range(3):
            status=self.dll.PdhGetFormattedCounterArrayW(self.counter,flags,ctypes.byref(size),ctypes.byref(count),None)
            if status==0 and size.value==0:return {}
            if status!=0x800007d2:self.check(status)  # PDH_MORE_DATA
            buffer=ctypes.create_string_buffer(size.value)
            status=self.dll.PdhGetFormattedCounterArrayW(self.counter,flags,ctypes.byref(size),ctypes.byref(count),buffer)
            if status==0x800007d2:continue  # Processes appeared while sizing.
            self.check(status)
            items=ctypes.cast(buffer,ctypes.POINTER(Item))
            return aggregate_engines((items[i].name,items[i].formatted.value,items[i].formatted.status) for i in range(count.value))
        raise OSError('GPU engine counter list changed repeatedly')
