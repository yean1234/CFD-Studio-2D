"""Report warehouse mesh size without generating cells or starting a solver."""
import argparse
import json
from pathlib import Path

from .porous_warehouse_mesh import mesh_plan


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,help='New JSON file; existing files are never overwritten')
    args=parser.parse_args()
    spec=json.loads(args.config.read_text(encoding='utf-8'))
    report=mesh_plan(spec)
    report['reference']=spec.get('resolution_reference')
    text=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if args.output:
        with args.output.open('x',encoding='utf-8') as stream:
            stream.write(text)
    print(text,end='')


if __name__=='__main__':
    main()
