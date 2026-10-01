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
