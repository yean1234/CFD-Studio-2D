"""Analysis forms and form-scoped presets, separate from immutable Case inputs."""
import copy
import uuid
import json

BUILTINS = (
    ('immersion', '이중액침냉각', 'config:immersion', ['icoReactingMultiphaseInterFoam']),
    ('grain_silo', '옥수수 사일로', 'config:grain_silo', ['simpleFoam', 'pimpleFoam']),
    ('warehouse', '식량 저장고 훈증 시스템', 'warehouse', ['warehouseBuoyantFoam']),
)


class CFDForms:
    def forms(self):
        from cfd_studio.execution_workspace import read_json
        overrides = read_json(self.folder/'forms.json', {})
        items = []
        for key, name, preset, solvers in BUILTINS:
            config = self.template(preset)
            if key == 'immersion':
                config['run'].setdefault('output_fields', ['bubble', 'phase', 'flow', 'therm'])
            items.append(overrides.pop(key, {'id': key, 'name': name, 'model': key,
                'description': '', 'solver': solvers[0], 'config': config, 'revision': 1, 'sections': {}}))
        items.extend(overrides.values())
        return [{**item, 'solvers': next(b[3] for b in BUILTINS if b[0] == item['model'])} for item in items]

    def form(self, key):
        found = next((f for f in self.forms() if f['id'] == key), None)
        if found is None:
            raise ValueError('CFD FORM을 선택하세요')
        return found

    def preset_form(self, key):
        from cfd_studio.execution_workspace import config_kind, read_json
        if key.startswith('form:'):
            return self.form(key[5:])['id']
        if key.startswith('scoped:'):
            path = self.preset_paths().get(key)
            if path is None:
                raise ValueError('프리셋을 찾을 수 없습니다')
            return read_json(path)['form_id']
        return config_kind(self.template(key))

    def project_form(self, project, records=None):
        if project.get('form_id'):
            return project['form_id']
        if project.get('default_preset'):
            return self.preset_form(project['default_preset'])
        models = [(records or {}).get(k, {}).get('model', '') for k in project.get('runs', [])]
        if 'immersion' in models:
            return 'immersion'
        if 'grain_silo' in models:
            return 'grain_silo'
        return 'warehouse'

    def check_form_config(self, form_id, config):
        from cfd_studio.execution_workspace import config_kind
        form = self.form(form_id)
        if config_kind(config) != form['model']:
            raise ValueError('프로젝트의 CFD FORM과 Config 해석 대상이 다릅니다')
        if form['model'] == 'grain_silo' and config.get('openfoam_mapping', {}).get('solver') != form['solver']:
            raise ValueError('CFD FORM에 지정된 솔버와 Config 솔버가 다릅니다')
        return form

    def check_form_preset(self, form_id, preset_id):
        self.form(form_id)
        if preset_id and self.preset_form(preset_id) != form_id:
            raise ValueError('선택한 CFD FORM에 속한 프리셋을 선택하세요')
        if preset_id:
            self.check_form_config(form_id, self.template(preset_id))

    def save_form(self, name, model, solver, config, form_id=None, revision=None, description='', sections=None):
        from cfd_studio.execution_workspace import label, config_kind, read_json, atomic_json
        name = label(name)
        json.dumps(config, allow_nan=False)
        from cfd_studio.execution_workspace import validate_settings
        validate_settings(config)
        if not isinstance(description, str) or len(description) > 4000:
            raise ValueError('FORM 설명은 4,000자 이내로 입력하세요')
        definition = next((b for b in BUILTINS if b[0] == model), None)
        if not definition or solver not in definition[3] or config_kind(config) != model:
            raise ValueError('지원되는 해석 대상·솔버·Config를 선택하세요')
        if model == 'grain_silo' and config.get('openfoam_mapping', {}).get('solver') != solver:
            raise ValueError('솔버와 Config가 일치하지 않습니다')
        sections = sections or {}
        if not isinstance(sections, dict) or any(k not in config or not isinstance(config[k], (dict, list)) for k in sections):
            raise ValueError('Config에 존재하는 입력 파트만 구성할 수 있습니다')
        sections = {k: label(v) for k, v in sections.items()}
        with self.lock:
            old = self.form(form_id) if form_id else None
            if old and old['revision'] != revision:
                raise ValueError('다른 화면에서 FORM이 변경되었습니다. 다시 열어 주세요.')
            if old and (old['model'] != model or old['solver'] != solver):
                raise ValueError('기존 FORM의 해석 대상·솔버는 고정됩니다. 새 FORM을 만드세요.')
            if any(f['id'] != form_id and f['name'].casefold() == name.casefold() for f in self.forms()):
                raise ValueError('같은 이름의 CFD FORM이 있습니다')
            key = form_id or 'custom_'+uuid.uuid4().hex
            item = {'id': key, 'name': name, 'model': model, 'solver': solver,
                'config': copy.deepcopy(config), 'description': description, 'sections': sections,
                'revision': old['revision']+1 if old else 1}
            data = read_json(self.folder/'forms.json', {})
            data[key] = item
            atomic_json(self.folder/'forms.json', data)
            return item

    def save_scoped_preset(self, name, config, form_id):
        from cfd_studio.execution_workspace import label, validate_settings, atomic_json
        name = label(name)
        self.check_form_config(form_id, config)
        validate_settings(config)
        with self.lock:
            folder = self.folder/'form_presets'
            if any(p['name'] == name and p['form_id'] == form_id for p in self.presets()):
                raise FileExistsError('같은 이름의 프리셋이 이 FORM에 있습니다')
            key = uuid.uuid4().hex
            atomic_json(folder/(key+'.json'), {'name': name, 'form_id': form_id, 'config': config})
            return {'id': 'scoped:'+key, 'name': name, 'form_id': form_id}
