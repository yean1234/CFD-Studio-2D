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


def blank_schema(config, schema=None):
    """Separate definition metadata from user values without rewriting legacy presets."""
    from cfd_studio.form_wizard import make_schema
    result=copy.deepcopy(schema or make_schema(config))
    def visit(fields,path=()):
        for field in fields:
            p=path+(field['key'],)
            fixed=(p[0]=='analysis' or (field['key']=='unit' and bool(field.get('value'))) or str(p[0]).startswith('_')
                   or p in (('numerics','algorithm'),('physics','flow_regime'),('termination','mode'),('openfoam_mapping','solver'),('openfoam_mapping','pressure_velocity_coupling'),('run','time_basis'),('outputs','fields'))
                   or field['key'] in ('model_options','method','state'))
            if field['type']=='object':visit(field['fields'],p)
            elif fixed:field['readonly']=True
            else:
                field.pop('readonly',None)
                field['nullable']=True
                field['value']=[] if field['type']=='array' else '' if field['type']=='string' else None
    visit(result['fields'])
    config_from_schema(result)
    return result


def validate_values(schema,config):
    """Validate Template keys/types and fixed metadata, preserving entered values."""
    def visit(fields,obj,path=''):
        if not isinstance(obj,dict):raise ValueError(path+' JSON 객체를 입력하세요')
        for field in fields:
            key=field['key'];name=path+'.'+key if path else key
            if key not in obj:raise ValueError(name+' 항목이 없습니다')
            value=obj[key]
            if field['type']=='object':visit(field['fields'],value,name)
            else:
                if field.get('required') and not field.get('readonly') and value in (None,'',[],{}):raise ValueError(name+' 값을 입력하세요')
                if field.get('readonly') and value!=field.get('value'):raise ValueError(name+' Template 정의는 변경할 수 없습니다')
                trial={'version':1,'fields':[{**field,'value':value}]}
                config_from_schema(trial)
    _json_value(config);visit(schema['fields'],config)
