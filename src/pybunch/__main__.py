import importlib.resources
import argparse
from functools import cached_property
from pathlib import Path
from dataclasses import dataclass
from typing import Dict

from . import packed_base
from .packed_base import DynamicLocalImporter


module = str


@dataclass(frozen=True)
class Project:
    package_mapping: Dict[Path, Path]
    sources_package: str = None

    @property
    def dynamic_local_importer(self):
        return DynamicLocalImporter(
            {'.'.join(relative_path.parts): absolute_path.read_text()
             for relative_path, absolute_path in self.package_mapping.items()},
            sources_package=self.sources_package
        )

    @cached_property
    def packed_code_base(self):
        packed_base_file = importlib.resources.files(packed_base) / 'packed_base.py'
        with packed_base_file.open("rt") as f:
            return f.read()

    def pack(self, entrypoint: str, statically_optimize: bool = False) -> str:
        entrypoint_path = Path(*entrypoint.split('.'))
        if entrypoint_path not in self.package_mapping:
            raise ValueError("Nonexistent entrypoint")

        included_packages = set(self.package_mapping.keys())
        if statically_optimize:
            dli = self.dynamic_local_importer
            dli.import_module(entrypoint)

            loaded_modules = dli.modules
            included_packages = {relative_path for relative_path in self.package_mapping
                                 if (relative_path in loaded_modules) or
                                 (relative_path.name == '__init__' and relative_path.parent in loaded_modules)}

        code_mapping = ',\n'.join(f'''\t'{'.'.join(pth.parts)}': """
{self.package_mapping[pth].read_text()}
"""''' for pth in included_packages)

        packed_code = self.packed_code_base + f"""\n
dli = DynamicLocalImporter({{
{code_mapping}
}}, sources_package={repr(sources_package)})
dli.execute_module('{entrypoint}')
"""

        return packed_code


if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='pybunch',
                                     description='Pack a python project into a single executable file')
    parser.add_argument('-r', '--root', type=Path, required=True, help='Project root')
    parser.add_argument('-e', '--entrypoint', required=True, type=module,
                        help='Entry point of python project, relative to the project root')
    parser.add_argument('-sp', '--sources-package', required=False, default=None, type=module,
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
    sources_package = args.sources_package
    statically_optimize = args.statically_optimize
    out_file = args.output

    project = Project({pth.relative_to(root).with_suffix(''): pth for pth in root.glob('**/*.py')},
                      sources_package=sources_package)
    out_file.write_text(project.pack(entrypoint, statically_optimize=statically_optimize))
