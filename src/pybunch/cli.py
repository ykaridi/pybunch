import argparse
from pathlib import Path
from typing import Tuple

from .packed_base import ModulePath
from .project import Project


def directory_argument(arg: str) -> Path:
    path = Path(arg)
    if not path.exists() and path.is_dir():
        raise ValueError("Directory not found")
    return path


def package_argument(arg: str) -> Tuple[ModulePath, Path]:
    if not arg.count('=') == 1:
        raise ValueError("Package must be of format name=path")
    package_name, package_path = arg.split('=')
    path = directory_argument(package_path)
    return ModulePath.from_name(package_name), path


def main():
    parser = argparse.ArgumentParser(prog='pybunch',
                                     description='Pack a python project into a single executable file')
    parser.add_argument('-d', '--directory', type=directory_argument, action='append',
                        help='Add directory to bundle')
    parser.add_argument('-p', '--package', type=package_argument, action='append',
                        help='Add a package to bundle. Format: <package_name>=<path>')
    parser.add_argument('-e', '--entrypoint', required=True, type=str,
                        help='Entry point of python project, relative to the project root')
    parser.add_argument('-so', '--statically-optimize', action='store_true',
                        help='Include only files that are statically imported from the entrypoint onwards')
    parser.add_argument('-o', '--output', required=False, type=Path, default=None,
                        help='Output path for packed file, default is to stdout.')

    args = parser.parse_args()
    directories = args.directory or []
    packages = args.package or []
    entrypoint = args.entrypoint
    statically_optimize = args.statically_optimize
    out_file = args.output

    module_mapping = {}
    for prefix, root in [(ModulePath(), d) for d in directories] + packages:
        for pyfile in root.glob('**/*.py'):
            module_path = prefix / ModulePath(*pyfile.relative_to(root).with_suffix('').parts)
            if module_path in module_mapping:
                raise ValueError(f"Duplicate entry for module str({module_path})")
            module_mapping[module_path] = pyfile

    project = Project(module_mapping)
    packed = project.pack(entrypoint, statically_optimize=statically_optimize)
    if out_file is not None:
        out_file.write_text(packed)
    else:
        print(packed)
