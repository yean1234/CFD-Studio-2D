"""User-defined Config fields; no geometry assumptions or solver execution."""
import copy
import json
import math

TYPES=('string','number','integer','boolean','object','array','null')
FORBIDDEN={'__proto__','prototype','constructor'}


def _json_value(value,depth=0):
    if depth>16:raise ValueError('Config nesting exceeds 16 levels')
    if isinstance(value,float) and not math.isfinite(value):raise ValueError('Config numbers must be finite')
    if isinstance(value,dict):
        for key,item in value.items():
            if key in FORBIDDEN:raise ValueError('Reserved Config key: '+key)
            _json_value(item,depth+1)
    elif isinstance(value,list):
        if len(value)>10000:raise ValueError('Config array is too large')
        for item in value:_json_value(item,depth+1)


def config_from_schema(schema):
    if not isinstance(schema,dict) or schema.get('version')!=1 or type(schema.get('version')) is not int:
        raise ValueError('Config schema version must be 1')
    count=0
    def group(fields,depth):
        nonlocal count
        if depth>16 or not isinstance(fields,list):raise ValueError('Invalid Config group')
        result={}
        for field in fields:
            count+=1
            if count>512 or not isinstance(field,dict):raise ValueError('Config supports up to 512 fields')
            key=field.get('key');kind=field.get('type')
            if not isinstance(key,str) or not key.strip() or len(key)>80 or key in FORBIDDEN:
                raise ValueError('Config Key must contain 1–80 characters and not be reserved')
            if key in result:raise ValueError('Duplicate Config Key: '+key)
            if kind not in TYPES:raise ValueError('Unsupported Config Type: '+str(kind))
            if not isinstance(field.get('unit',''),str) or len(field.get('unit',''))>64:
                raise ValueError('Config Unit must contain at most 64 characters')
            if kind=='object':value=group(field.get('fields'),depth+1)
            else:
                if 'value' not in field:raise ValueError('Config Value is missing: '+key)
                value=field['value']
                if 'nullable' in field and type(field['nullable']) is not bool:raise ValueError('Invalid nullable flag')
                valid={'string':lambda:type(value) is str,'number':lambda:type(value) in (int,float),
                       'integer':lambda:type(value) is int,'boolean':lambda:type(value) is bool,
                       'array':lambda:type(value) is list,'null':lambda:value is None}[kind]()
                if not valid and not (field.get('nullable') is True and value is None):raise ValueError('Config Value does not match Type: '+key)
                _json_value(value,depth+1)
            result[key]=copy.deepcopy(value)
        return result
    result=group(schema.get('fields'),0)
    json.dumps(result,allow_nan=False)
    return result


def validate_schema(schema,config):
    derived=config_from_schema(schema)
    if json.dumps(derived,sort_keys=True,allow_nan=False)!=json.dumps(config,sort_keys=True,allow_nan=False):
        raise ValueError('Config and field schema do not match')


def is_geometry_path(path):
    if 'properties' in path:return False
    root=path[0] if path else ''
    key=path[1] if len(path)>1 else ''
    if root in ('geometry','domain','regions','geometry_spec','loading','silo','published','probes_mm'):return True
    if root in ('dielectric_fluid','water'):return key in ('name','role','material_state','state','_transform_reference','config_bindings')
    if root in ('tank','board','coil'):return key in ('shape','unit','min','max','center','radius','height','axis','width_mm','depth_mm','liquid_height_mm','x0','x1','y0','y1','z0','z1','name','role','material_state','state','_transform_reference','config_bindings')
    if root=='layers':return key in ('dielectric_mm','air_mm')
    return root=='heater' and key=='cpus'


def _blank_property_values(value):
    if isinstance(value,list):
        for item in value:_blank_property_values(item)
    elif isinstance(value,dict):
        properties=value.get('properties')
        if isinstance(properties,dict):
            for record in properties.values():
                if isinstance(record,dict) and record.get('type') in TYPES and 'value' in record:
                    record['value']=[] if record['type']=='array' else '' if record['type']=='string' else None
        for item in value.values():_blank_property_values(item)


def _blank_property_fields(fields):
    for field in fields:
        if field['type']=='object':
            if field['key']=='properties':
                for record in field['fields']:
                    parts={f['key']:f for f in record.get('fields',[])}
                    kind=parts.get('type',{}).get('value')
                    if kind in TYPES and 'value' in parts:
                        item=parts['value'];item.pop('readonly',None);item['nullable']=True
                        item['value']=[] if kind=='array' else '' if kind=='string' else None
            _blank_property_fields(field['fields'])
        elif isinstance(field.get('value'),(dict,list)):_blank_property_values(field['value'])


def _inherit_property_values(layout, previous):
    """Template dimensions can change; values stay attached to matching named parts."""
    if isinstance(layout,list) and isinstance(previous,list):
        named={x.get('name'):x for x in previous if isinstance(x,dict) and x.get('name')}
        for i,item in enumerate(layout):
            prior=named.get(item.get('name'),{}) if isinstance(item,dict) and item.get('name') else previous[i] if i<len(previous) else None
            _inherit_property_values(item,prior)
    elif isinstance(layout,dict) and isinstance(previous,dict):
        for key,value in layout.items():
            prior=previous.get(key)
            if key=='properties' and isinstance(value,dict) and isinstance(prior,dict):
                for name,record in value.items():
                    old=prior.get(name)
                    if isinstance(record,dict) and isinstance(old,dict) and 'value' in record and old.get('type')==record.get('type'):
                        record['value']=copy.deepcopy(old.get('value'))
            else:_inherit_property_values(value,prior)


def blank_schema(config, schema=None):
    """Separate definition metadata from user values without rewriting legacy presets."""
    from cfd_studio.form_wizard import make_schema
    result=copy.deepcopy(schema or make_schema(config))
    # Restore geometry from older templates whose input schema blanked dimensions.
    if schema and schema.get('spatial_version')!=1:
        def with_metadata(source,old):
            value=copy.deepcopy(source)
            for key in ('label','description','required'):
                if key in old:value[key]=copy.deepcopy(old[key])
            if value['type']=='object' and old['type']=='object':
                prior={f['key']:f for f in old['fields']}
                value['fields']=[with_metadata(f,prior[f['key']]) if f['key'] in prior else f for f in value['fields']]
            return value
        def restore(fields,original,path=()):
            by_key={f['key']:f for f in original}
            for i,field in enumerate(fields):
                p=path+(field['key'],);source=by_key.get(field['key'])
                if source is None:continue
                if is_geometry_path(p):fields[i]=with_metadata(source,field)
                elif field['type']=='object' and source['type']=='object':restore(field['fields'],source['fields'],p)
        restore(result['fields'],make_schema(config)['fields'])
    result['spatial_version']=1
    def visit(fields,path=()):
        for field in fields:
            p=path+(field['key'],)
            fixed=(p[0]=='analysis' or (field['key']=='unit' and bool(field.get('value'))) or str(p[0]).startswith('_')
                   or p in (('numerics','algorithm'),('physics','flow_regime'),('termination','mode'),('openfoam_mapping','solver'),('openfoam_mapping','pressure_velocity_coupling'),('run','time_basis'),('outputs','fields'))
                   or field['key'] in ('model_options','method','state'))
            if field['key']=='properties' and field['type']=='object' and all(r['type']=='object' and {'type','value'} <= {f['key'] for f in r['fields']} for r in field['fields']):continue
            if is_geometry_path(p):
                def editable(f):
                    f.pop('readonly',None)
                    if f['type']=='object':
                        for child in f['fields']:editable(child)
                editable(field)
                continue
            if field['type']=='object':visit(field['fields'],p)
            elif fixed:field['readonly']=True
            else:
                field.pop('readonly',None)
                field['nullable']=True
                field['value']=[] if field['type']=='array' else '' if field['type']=='string' else None
    visit(result['fields'])
    _blank_property_fields(result['fields'])
    config_from_schema(result)
    return result


def apply_initial_geometry(config,schema):
    """Copy editable layout defaults only; never replace operating preset values."""
    result=copy.deepcopy(config)
    def visit(fields,target,path=()):
        for field in fields:
            key=field['key'];p=path+(key,)
            if is_geometry_path(p):
                layout=config_from_schema({'version':1,'fields':[field]})[key]
                _inherit_property_values(layout,target.get(key))
                target[key]=layout
            elif field['type']=='object' and isinstance(target.get(key),dict):visit(field['fields'],target[key],p)
    visit(schema['fields'],result)
    return result


def validate_geometry(config):
    """Check supported primitive dimensions before a project can use them."""
    def number(value):return type(value) in (int,float) and math.isfinite(value)
    def vector(value):return isinstance(value,list) and len(value)==3 and all(number(v) for v in value)
    def region(value):
        if not isinstance(value,dict):return
        shape=value.get('shape',value.get('type'))
        if shape not in ('box','sphere','cylinder'):return  # External/custom geometry has its own adapter.
        if value.get('unit') not in ('m','cm','mm'):raise ValueError('형상 단위에 m, cm 또는 mm를 입력하세요')
        if shape=='box':
            low,high=value.get('min'),value.get('max')
            if not vector(low) or not vector(high) or any(a>=b for a,b in zip(low,high)):raise ValueError('형상의 최소·최대 좌표를 확인하세요')
        else:
            if not vector(value.get('center')) or not number(value.get('radius')) or value['radius']<=0:raise ValueError('형상의 중심 좌표와 반지름을 확인하세요')
            if shape=='cylinder' and (not number(value.get('height')) or value['height']<=0 or value.get('axis') not in ('x','y','z')):raise ValueError('원기둥의 높이와 중심축을 확인하세요')
    def collection(value,unit=None):
        for item in value if isinstance(value,list) else value.values() if isinstance(value,dict) else ():
            if isinstance(item,dict):region({'unit':unit,**item})
    geometry=config.get('geometry',{})
    if isinstance(geometry,dict):
        region(geometry)
        for key in ('regions','fluid_regions','solid_regions'):collection(geometry.get(key),geometry.get('unit'))
    region(config.get('domain'));collection(config.get('regions'))
    for key in ('tank','board','coil'):region(config.get(key))
    loading=config.get('loading')
    if isinstance(loading,dict):collection(loading.get('blocks'))


def validate_values(schema,config):
    """Validate Template keys/types and fixed metadata, preserving entered values."""
    def visit(fields,obj,path=''):
        if not isinstance(obj,dict):raise ValueError(path+' JSON 객체를 입력하세요')
        for field in fields:
            key=field['key'];name=path+'.'+key if path else key
            if key not in obj:raise ValueError(name+' 항목이 없습니다')
            value=obj[key]
            # Geometry collections are project-owned: additions/removals are permitted.
            if is_geometry_path(tuple(name.split('.'))):
                from cfd_studio.form_wizard import make_schema
                if field['type']=='object':
                    if not isinstance(value,dict):raise ValueError(name+' JSON 객체를 입력하세요')
                    config_from_schema(make_schema(value))
                else:config_from_schema({'version':1,'fields':[{**field,'value':value}]})
                continue
            if field['type']=='object':visit(field['fields'],value,name)
            else:
                if field.get('required') and not field.get('readonly') and value in (None,'',[],{}):raise ValueError(name+' 값을 입력하세요')
                if field.get('readonly') and value!=field.get('value'):raise ValueError(name+' Template 정의는 변경할 수 없습니다')
                trial={'version':1,'fields':[{**field,'value':value}]}
                config_from_schema(trial)
    _json_value(config);visit(schema['fields'],config);validate_geometry(config)
