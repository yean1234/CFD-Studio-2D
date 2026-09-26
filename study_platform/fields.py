"""저장된 장의 후처리 조회 전용. 곤충이나 행동 모델을 포함하지 않는다."""
from pathlib import Path
from tracer_transport.sample import ConcentrationField
from .service import file_hash


class FieldProvider:
    def __init__(self, path):
        self.field = ConcentrationField(path)
        self.artifact = {'name': Path(path).name, 'sha256': file_hash(path)}

    def query(self, position, time_s, field='concentration', region_id=None):
        if field != 'concentration':
            return {'valid': False, 'reason': 'field_unavailable', 'value': None,
                    'unit': None, 'source_artifact': self.artifact}
        value = self.field.sample_concentration(position, time_s, region_id)
        return {'value': value['concentration'], 'valid': value['valid'],
                'reason': value.get('reason'), 'unit': 'pore C/C_ref',
                'region_id': value.get('region_id'), 'source_artifact': self.artifact,
                'interpolation': {'space': 'containing_cell_no_cross_boundary', 'time': 'linear'}}
