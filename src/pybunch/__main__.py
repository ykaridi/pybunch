import importlib.resources
import argparse
from pathlib import Path

from . import packed_base


if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='pybunch',
                                     description='Pack a python project into a single executable file')
    parser.add_argument('-r', '--root', type=Path, required=True, help='Project root')
    parser.add_argument('-e', '--entrypoint', required=True, type=Path,
                        help='Entry point of python project, relative to the project root')
    parser.add_argument('-o', '--output', required=True, type=Path,
                        help='Output path for packed file')

    args = parser.parse_args()
    root = args.root
    out_file = args.output
    entrypoint = args.entrypoint

    if not (root / entrypoint.with_suffix('.py')).exists():
        raise ValueError("Nonexistent entrypoint")

    packed_base_file = importlib.resources.files(packed_base) / 'packed_base.py'
    with packed_base_file.open("rt") as f:
        packed_base_code = f.read()

    codes_code = ',\n'.join(f'''\t'{'.'.join(pth.relative_to(root).with_suffix('').parts)}': """
{pth.read_text()}
"""''' for pth in root.glob('**/*.py'))

    packed_code = packed_base_code + f"""

dli = DynamicLocalImporter({{
{codes_code}
}})
dli.execute('{'.'.join(entrypoint.parts)}')
"""

    out_file.write_text(packed_code)
