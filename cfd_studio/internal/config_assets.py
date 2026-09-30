"""Immutable, owner-local Config definitions; these are not solver mesh outputs."""
import hashlib
import json
import tempfile
from pathlib import Path

GEOMETRY_KEYS=('geometry','geometry_spec','domain','regions','tank','layers','board','coil','heater','loading','silo','published')
MESH_KEYS=('mesh','porous_mesh')


def store_definitions(owner, config):
    """Publish a complete content-addressed bundle before its owner references it.

    No supplied source path is opened or modified. External imports remain explicit.
    A failed owner save may leave an unreferenced bundle, never overwrite prior inputs.
    """
    if not isinstance(config,dict):raise ValueError('Config must be an object')
    encoded=json.dumps(config,ensure_ascii=False,sort_keys=True,allow_nan=False).encode('utf-8')
    digest=hashlib.sha256(encoded).hexdigest()
    relative=Path('Assets')/'Definitions'/digest
    target=Path(owner)/relative
    sections={key:'Sections/'+hashlib.sha256(key.encode('utf-8')).hexdigest()[:20]+'.json' for key in config}
    files={'config.json':config,
           'geometry.json':{key:config[key] for key in GEOMETRY_KEYS if key in config},
           'mesh.json':{key:config[key] for key in MESH_KEYS if key in config}}
    files.update({sections[key]:value for key,value in config.items()})
    files['manifest.json']={'schema':1,'kind':'config_definitions','config_sha256':digest,'sections':sections,
                            'geometry':'geometry.json','mesh':'mesh.json','solver_mesh_generated':False}
    if target.exists():
        for name,value in files.items():
            if json.loads((target/name).read_text(encoding='utf-8'))!=value:raise ValueError('저장된 Config 정의 파일이 변경되었습니다: '+name)
    else:
        target.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.definitions-',dir=target.parent) as temporary:
            staging=Path(temporary)/'bundle';staging.mkdir()
            for name,value in files.items():
                path=staging/name;path.parent.mkdir(exist_ok=True)
                path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
            staging.rename(target)
    return {'schema':1,'root':relative.as_posix(),'config':'config.json','geometry':'geometry.json','mesh':'mesh.json','sections':sections}
