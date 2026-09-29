"""Analysis forms and form-scoped presets, separate from immutable Case inputs."""
import copy
import uuid
import json

from pathlib import Path

_DEFINITIONS = json.loads((Path(__file__).resolve().parents[1]/'templates/cfd-forms.json').read_text(encoding='utf-8'))
BUILTINS = tuple((item['id'], item['name'], item['template'], item['solvers']) for item in _DEFINITIONS['forms'])



# Defaults belong to the connected input adapter, not to UI branches.
FORM_OUTPUTS = {
    'immersion': {'default_output_fields': ['bubble', 'phase', 'flow', 'therm'],
                  'output_fields': ['bubble', 'phase', 'flow', 'therm', 'pressure', 'turbulence']},
    'grain_silo': {'output_fields': ['flow', 'pressure', 'turbulence']},
}


def prepare_config(config, model):
    value = copy.deepcopy(config)
    defaults = FORM_OUTPUTS.get(model, {}).get('default_output_fields')
    if defaults is not None:
        value.setdefault('run', {}).setdefault('output_fields', list(defaults))
    return value


class CFDForms:
    def forms(self):
        from cfd_studio.execution_workspace import read_json
        overrides = read_json(self.folder/'forms.json', {})
        items = []
        for key, name, preset, solvers in BUILTINS:
            config = self.template(preset)
            config = prepare_config(config, key)
            items.append(overrides.pop(key, {'id': key, 'name': name, 'model': key,
                'description': '', 'solver': solvers[0], 'config': config, 'revision': 1, 'sections': {}}))
        items.extend(overrides.values())
        from cfd_studio.result_series import output_definitions
        return [{**item, 'capabilities': copy.deepcopy(FORM_OUTPUTS.get(item['model'], {})), 'outputs': output_definitions(item['model']),
                 'definition_only':item['model']=='solver_definition',
                 'solvers':next((b[3] for b in BUILTINS if b[0] == item['model']),[item['solver']])} for item in items]

    def form_templates(self):
        """Connected templates by solver; UI never constructs solver input defaults."""
        from cfd_studio.solver_catalog import definition, result_axis
        forms = {f['id']: f for f in self.forms()}
        templates = []
        for key, _, _, solvers in BUILTINS:
            form = forms[key]
            for solver in solvers:
                config = prepare_config(form['config'], key)
                options = definition(solver)
                if options.get('coupling') and 'openfoam_mapping' in config:
                    config['openfoam_mapping']['solver'] = solver
                    config['openfoam_mapping']['pressure_velocity_coupling'] = options['coupling']
                    config['run']['time_basis'] = 'iterations' if result_axis({'solver': solver}) == 'iteration' else 'physical_time'
                    config.pop('_studio', None)
                templates.append({'model': key, 'name': form['name'], 'solver': solver,
                                  'config': config, 'outputs': form['outputs']})
        return templates

    def solver_catalog(self, check=False):
        from cfd_studio.solver_catalog import catalog, probe
        if check:
            self._solver_installation=probe(self.settings)
        installation=getattr(self,'_solver_installation',None)
        return {'solvers':catalog(installation),'installation':installation}

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
        known = {b[0] for b in BUILTINS}
        models = set()
        for key in project.get('runs', []):
            record = (records or {}).get(key, {})
            model = 'warehouse' if record.get('kind') == 'warehouse' else record.get('model')
            if model not in known:
                return None
            models.add(model)
        return next(iter(models)) if len(models) == 1 else None

    def check_form_config(self, form_id, config):
        from cfd_studio.execution_workspace import config_kind
        form = self.form(form_id)
        if form.get('definition_only'):
            raise ValueError('솔버 FORM 초안입니다. 입력 생성·실행·결과 읽기 연결 후 Case를 만들 수 있습니다.')
        if config_kind(config) != form['model']:
            raise ValueError('프로젝트의 CFD FORM과 Config 해석 대상이 다릅니다')
        if form['model'] == 'grain_silo' and config.get('openfoam_mapping', {}).get('solver') != form['solver']:
            raise ValueError('CFD FORM에 지정된 솔버와 Config 솔버가 다릅니다')
        return form

    def check_form_preset(self, form_id, preset_id):
        if self.form(form_id).get('definition_only'):
            raise ValueError('솔버 FORM 초안은 프로젝트에 적용할 수 없습니다. Studio 연결이 필요합니다.')
        if preset_id and self.preset_form(preset_id) != form_id:
            raise ValueError('선택한 CFD FORM에 속한 프리셋을 선택하세요')
        if preset_id:
            self.check_form_config(form_id, self.template(preset_id))

    def save_form(self, name, model, solver, config, form_id=None, revision=None, description='', sections=None, config_schema=None):
        from cfd_studio.execution_workspace import label, config_kind, read_json, atomic_json
        name = label(name)
        json.dumps(config, allow_nan=False)
        from cfd_studio.execution_workspace import validate_settings
        from cfd_studio.solver_catalog import definition as solver_definition, validate_draft
        solver_definition(solver)
        if config_schema is not None:
            from cfd_studio.form_schema import validate_schema
            validate_schema(config_schema,config)
        if model=='solver_definition':
            analysis=config.get('analysis',{}) if isinstance(config,dict) else {}
            if isinstance(analysis,dict) and analysis.get('form_generator')=='solver-questionnaire-v1':
                from cfd_studio.form_wizard import generate
                generated=generate(solver,analysis.get('choices'))
                if analysis.get('solver')!=solver or analysis.get('time_mode')!=generated['config']['analysis']['time_mode']:
                    raise ValueError('JSON의 솔버·해석 방식이 FORM과 다릅니다')
            if config_schema is None:
                validate_draft(config,solver)  # Preserve older input-plan drafts.
        else:
            validate_settings(config)
        if not isinstance(description, str) or len(description) > 4000:
            raise ValueError('FORM 설명은 4,000자 이내로 입력하세요')
        definition = next((b for b in BUILTINS if b[0] == model), None)
        if model!='solver_definition' and (not definition or solver not in definition[3] or config_kind(config) != model):
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
            if config_schema is not None:
                item['config_schema']=copy.deepcopy(config_schema)
            if model=='solver_definition' and isinstance(config.get('analysis'),dict) and config['analysis'].get('form_generator')=='solver-questionnaire-v1':
                from cfd_studio.solver_requirements import inspect_config
                item['input_review']=inspect_config(solver,config)
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
