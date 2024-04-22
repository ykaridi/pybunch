import importlib.resources
import argparse
from pathlib import Path

from . import packed_base


module = str


if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='pybunch',
                                     description='Pack a python project into a single executable file')
    parser.add_argument('-r', '--root', type=Path, required=True, help='Project root')
    parser.add_argument('-e', '--entrypoint', required=True, type=module,
                        help='Entry point of python project, relative to the project root')
    parser.add_argument('-sp', '--sources-package', required=False, default=None, type=module,
                        help='Package for bundled sources, allowing to import them with absolute imports'
                             ' to that package')
    parser.add_argument('-o', '--output', required=True, type=Path,
                        help='Output path for packed file')

    args = parser.parse_args()
    root = args.root
    entrypoint = args.entrypoint
    entrypoint_path = Path(*entrypoint.split('.'))
    sources_package = args.sources_package
    out_file = args.output

    if not (root / entrypoint_path.with_suffix('.py')).exists():
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
}}, sources_package={repr(sources_package)})
dli.execute('{entrypoint}')
"""

    out_file.write_text(packed_code)
