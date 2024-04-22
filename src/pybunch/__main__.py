import importlib.resources
import argparse
from functools import cached_property
from pathlib import Path
from typing import Dict

from . import packed_base
from .packed_base import DynamicLocalImporter, ModulePath, ModuleDescription


module = str


class Project:
    def __init__(self, package_mapping: Dict[ModulePath, Path], package: str):
        if package is not None:
            package_mapping = {ModulePath(package) / relative_path: absolute_path
                               for relative_path, absolute_path in package_mapping.items()}
        self._package_mapping = package_mapping
        self._package = package

    @property
    def dynamic_local_importer(self):
        module_descriptions = {}
        for relative_path, absolute_path in self._package_mapping.items():
            name = '.'.join(relative_path.parts)
            module_descriptions[name] = ModuleDescription(name, code=absolute_path.read_text())

        return DynamicLocalImporter(module_descriptions)

    @cached_property
    def packed_code_base(self):
        packed_base_file = importlib.resources.files(packed_base) / 'packed_base.py'
        with packed_base_file.open("rt") as f:
            return f.read()

    def pack(self, entrypoint: str, statically_optimize: bool = False) -> str:
        entrypoint_path = ModulePath.from_name(entrypoint)
        if self._package is not None and entrypoint_path.parts[0] != self._package:
            entrypoint_path = ModulePath(self._package) / entrypoint_path
        if entrypoint_path not in self._package_mapping:
            raise ValueError("Nonexistent entrypoint")
        entrypoint = str(entrypoint_path)

        included_packages = set(self._package_mapping.keys())
        if statically_optimize:
            dli = self.dynamic_local_importer
            dli.import_module(entrypoint)

            loaded_modules = {ModulePath.from_name(name) for name in dli.loaded_modules}
            included_packages = {relative_path for relative_path in self._package_mapping
                                 if (relative_path in loaded_modules) or
                                 (relative_path.name == '__init__' and relative_path.parent in loaded_modules)}

        package_entries = []
        for pth in included_packages:
            name = '.'.join(pth.parts)
            code = f'''\t'{name}': ModuleDescription('{name}', code="""
{self._package_mapping[pth].read_text()}
""")'''
            package_entries.append(code)

        packed_code = self.packed_code_base + f"""\n
dli = DynamicLocalImporter({{
{',\n'.join(package_entries)}
}})
dli.execute_module('{entrypoint}')
"""

        return packed_code


if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='pybunch',
                                     description='Pack a python project into a single executable file')
    parser.add_argument('-r', '--root', type=Path, required=True, help='Project root')
    parser.add_argument('-e', '--entrypoint', required=True, type=module,
                        help='Entry point of python project, relative to the project root')
    parser.add_argument('-p', '--package', required=False, default=None, type=module,
                        help='Package for bundled sources, allowing to import them with absolute imports'
                             ' to that package')
    parser.add_argument('-so', '--statically-optimize', action='store_true',
                        help='Include only files that are statically imported from the entrypoint'
                             ' (executes code to determine)')
    parser.add_argument('-o', '--output', required=True, type=Path,
                        help='Output path for packed file')

    args = parser.parse_args()
    root = args.root
    entrypoint = args.entrypoint
    package = args.package
    statically_optimize = args.statically_optimize
    out_file = args.output

    project = Project({ModulePath(*pth.relative_to(root).with_suffix('').parts): pth for pth in root.glob('**/*.py')},
                      package)
    out_file.write_text(project.pack(entrypoint, statically_optimize=statically_optimize))
