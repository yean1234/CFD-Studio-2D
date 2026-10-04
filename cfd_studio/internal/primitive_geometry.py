"""Compatibility checks for explicit geometry used by existing box-only runners."""
import math


def validate_runner_geometry(config):
    """Reject visual geometry that an existing adapter would otherwise ignore.

    This does not alter inputs or add mesh-generation support to a solver.
    """
    def check(part,expected_min,expected_max,unit):
        if not isinstance(part,dict) or 'shape' not in part:return
        if part['shape']!='box':
            raise ValueError('현재 실행기는 이 영역의 직육면체 형상만 지원합니다')
        scale={'m':1.,'cm':.01,'mm':.001}.get(part.get('unit'))
        if scale is None:raise ValueError('형상 단위에 m, cm 또는 mm를 입력하세요')
        scale_old={'m':1.,'mm':.001}[unit]
        for key,expected in [('min',expected_min),('max',expected_max)]:
            actual=part.get(key)
            if not isinstance(actual,list) or len(actual)!=3 or not isinstance(expected,list) or len(expected)!=3 or any(
                type(a) not in (int,float) or type(b) not in (int,float)
                or not math.isfinite(a) or not math.isfinite(b)
                or not math.isclose(a*scale,b*scale_old,abs_tol=1e-9,rel_tol=1e-10)
                for a,b in zip(actual,expected)
            ):raise ValueError('명시한 형상과 기존 실행기 치수가 다릅니다 · 형상 JSON에서 다시 저장하세요')
    tank=config.get('tank')
    if isinstance(tank,dict):
        check(tank,[0,0,0],[tank.get('width_mm'),tank.get('liquid_height_mm'),tank.get('depth_mm')],'mm')
        for key in ('board','coil'):
            p=config.get(key)
            if isinstance(p,dict):check(p,[p.get(k) for k in ('x0','y0','z0')],[p.get(k) for k in ('x1','y1','z1')],'mm')
    loading=config.get('loading')
    blocks=loading.get('blocks') if isinstance(loading,dict) else None
    for p in blocks if isinstance(blocks,list) else ():
        if isinstance(p,dict):check(p,p.get('min_m',[None]*3),p.get('max_m',[None]*3),'m')


def validate_fill_definitions(config):
    """Check explicit interior/fill records and their cached primitive geometry."""
    scales={'m':1.,'cm':.01,'mm':.001}
    def at(path):
        node=config
        if not isinstance(path,list) or not path:raise ValueError('채움 기준 공간을 선택하세요')
        try:
            for key in path:
                if key in ('__proto__','prototype','constructor'):raise ValueError('Invalid reference')
                if isinstance(node,list) and (type(key) is not int or key<0):raise ValueError('Invalid reference')
                node=node[key]
        except (KeyError,IndexError,TypeError):raise ValueError('채움 기준 공간을 찾을 수 없습니다') from None
        return node
    def finite(v):return type(v) in (int,float) and math.isfinite(v)
    def primitive(p):
        if not isinstance(p,dict):raise ValueError('공간 형상을 확인하세요')
        if p.get('shape') in ('box','cylinder'):
            return p
        if all(k in p for k in ('width_mm','liquid_height_mm','depth_mm')):
            return {'shape':'box','unit':'mm','min':[0,0,0],'max':[p['width_mm'],p['liquid_height_mm'],p['depth_mm']]}
        raise ValueError('채움은 직육면체 또는 원기둥 공간을 지원합니다')
    fills=[]
    def interior(part):
        inner=primitive(part['interior']);outer=primitive(part)
        if inner.get('shape')!=outer.get('shape'):raise ValueError('내부 공간은 외곽과 같은 기본 형상으로 정의하세요')
        try:
            scale=scales[inner['unit']]/scales[outer['unit']]
            if inner['shape']=='box':
                coordinates=[inner['min'],inner['max'],outer['min'],outer['max']]
                if not all(isinstance(v,list) and len(v)==3 and all(finite(x) for x in v) for v in coordinates):raise ValueError('내부 공간 좌표를 확인하세요')
                inside=all(outer['min'][i]<=a*scale<b*scale<=outer['max'][i] for i,(a,b) in enumerate(zip(inner['min'],inner['max'])))
            else:
                a='xyz'.index(inner['axis']);other=[i for i in range(3) if i!=a]
                numbers=[*inner['center'],*outer['center'],inner['radius'],inner['height'],outer['radius'],outer['height']]
                if not all(finite(x) for x in numbers) or min(inner['radius'],inner['height'],outer['radius'],outer['height'])<=0:raise ValueError('내부 공간 치수를 확인하세요')
                inside=inner['axis']==outer['axis'] and math.hypot(*(inner['center'][i]*scale-outer['center'][i] for i in other))+inner['radius']*scale<=outer['radius'] and abs(inner['center'][a]*scale-outer['center'][a])+inner['height']*scale/2<=outer['height']/2
        except (KeyError,TypeError,IndexError):raise ValueError('내부 공간 치수와 단위를 확인하세요') from None
        if not inside:raise ValueError('내부 공간이 고체 외곽을 벗어났습니다')
    def visit(v,path=()):
        if isinstance(v,list):
            for i,x in enumerate(v):visit(x,path+(i,))
        elif isinstance(v,dict):
            if 'interior' in v:interior(v)
            if 'fill' in v:
                fill=v['fill']
                if not isinstance(fill,dict):raise ValueError('공간 채움 정의를 확인하세요')
                parent=at(fill.get('container_path'))
                if parent is v or not isinstance(parent,dict) or parent.get('fill') or parent.get('material_state',parent.get('state')) in ('liquid','gas','mesh_refinement'):
                    raise ValueError('유체 영역을 채움 기준 공간으로 사용할 수 없습니다')
                if parent.get('material_state',parent.get('state'))=='solid' and not parent.get('interior'):
                    raise ValueError('고체의 내부 공간을 먼저 정의하세요')
                p=primitive(parent.get('interior',parent))
                start,end,unit,axis=(fill.get(k) for k in ('start','end','unit','axis'))
                if unit not in scales or p.get('unit') not in scales or axis not in ('x','y','z') or not finite(start) or not finite(end) or start<0 or end<=start:
                    raise ValueError('채움 시작·끝 위치와 단위를 확인하세요')
                index='xyz'.index(axis);scale=scales[unit]/scales[p['unit']];start*=scale;end*=scale
                if p['shape']=='box':
                    lo,hi=p.get('min'),p.get('max')
                    if not all(isinstance(x,list) and len(x)==3 and all(finite(a) for a in x) for x in (lo,hi)) or any(b<=a for a,b in zip(lo,hi)):
                        raise ValueError('내부 공간 좌표를 확인하세요')
                    extent=hi[index]-lo[index];expected_min=list(lo);expected_max=list(hi);expected_min[index]+=start;expected_max[index]=lo[index]+end
                    expected={'min':expected_min,'max':expected_max}
                else:
                    if p.get('axis')!=axis or not finite(p.get('height')) or p['height']<=0 or not finite(p.get('radius')) or p['radius']<=0:
                        raise ValueError('원기둥 채움 방향과 치수를 확인하세요')
                    center=p.get('center')
                    if not isinstance(center,list) or len(center)!=3 or not all(finite(x) for x in center):raise ValueError('내부 공간 좌표를 확인하세요')
                    extent=p['height'];center=list(center);center[index]+=-extent/2+(start+end)/2;expected={'center':center,'height':end-start,'radius':p['radius'],'axis':axis}
                if end>extent+1e-10:raise ValueError('채움 범위가 내부 공간을 벗어났습니다')
                if v.get('shape')!=p['shape'] or v.get('unit')!=p['unit']:raise ValueError('채움 정의와 형상이 다릅니다 · 채움을 다시 적용하세요')
                for key,value in expected.items():
                    actual=v.get(key)
                    if isinstance(value,list):equal=isinstance(actual,list) and len(actual)==len(value) and all(finite(a) and math.isclose(a,b,abs_tol=1e-9) for a,b in zip(actual,value))
                    elif isinstance(value,str):equal=actual==value
                    else:equal=finite(actual) and math.isclose(actual,value,abs_tol=1e-9)
                    if not equal:raise ValueError('채움 정의와 형상이 다릅니다 · 채움을 다시 적용하세요')
                fills.append(v)
                if path in (('dielectric_fluid',),('water',)) and isinstance(config.get('tank'),dict) and isinstance(config.get('layers'),dict):
                    boundary=config['layers'].get('dielectric_mm');height=config['tank'].get('liquid_height_mm');factor=scales[unit]/.001
                    expected_start,expected_end=(0,boundary) if path[0]=='dielectric_fluid' else (boundary,height)
                    if fill['container_path']!=['tank'] or axis!='y' or parent.get('interior') or not finite(expected_start) or not finite(expected_end) or not math.isclose(fill['start']*factor,expected_start) or not math.isclose(fill['end']*factor,expected_end):
                        raise ValueError('기존 실행기는 같은 공간의 연속된 두 유체층만 지원합니다')
            for k,x in v.items():visit(x,path+(k,))
    visit(config)
    for i,a in enumerate(fills):
        for b in fills[i+1:]:
            if a['fill']['container_path']!=b['fill']['container_path']:continue
            if a['shape']=='box':overlap=all(min(a['max'][k],b['max'][k])-max(a['min'][k],b['min'][k])>1e-10 for k in range(3))
            else:
                k='xyz'.index(a['axis']);overlap=min(a['center'][k]+a['height']/2,b['center'][k]+b['height']/2)-max(a['center'][k]-a['height']/2,b['center'][k]-b['height']/2)>1e-10
            if overlap:raise ValueError('채움 범위가 다른 유체 영역과 겹칩니다')
