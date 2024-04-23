import importlib.resources
from functools import cached_property
from pathlib import Path
from typing import Dict

from . import packed_base
from .packed_base import DynamicLocalImporter, ModulePath, ModuleDescription


class Project:
    def __init__(self, package_mapping: Dict[ModulePath, Path], package: str):
        if package is not None:
            package_mapping = {ModulePath(package) / relative_path: absolute_path
                               for relative_path, absolute_path in package_mapping.items()}
        self._package_mapping = package_mapping
        self._package = package

    @property
    def dynamic_local_importer(self) -> DynamicLocalImporter:
        module_descriptions = {}
        for relative_path, absolute_path in self._package_mapping.items():
            name = '.'.join(relative_path.parts)
            module_descriptions[name] = ModuleDescription(name, code=absolute_path.read_text())

        return DynamicLocalImporter(module_descriptions)

    @cached_property
    def packed_code_base(self) -> str:
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

        code_entries = []
        package_entries = []
        for pth in included_packages:
            name = '.'.join(pth.parts)
            escaped_name = 'PYBUNCH_%s' % '_'.join(pth.parts).upper()
            code = self._package_mapping[pth].read_text()
            escaped_code = code.replace('"', '\\"')

            code_entries.append(f'# Code for module <{name}>\n{escaped_name} = """\n{escaped_code}\n"""[1:]')
            package_entries.append(f"'{name}': ModuleDescription('{name}', code={escaped_name})")

        header = ''.join(entry + "\n\n\n" for entry in code_entries)
        footer = f"""\n\n
dli = DynamicLocalImporter({{
{',\n'.join("    %s" % entry for entry in package_entries)}
}})
dli.execute_module('{entrypoint}')
"""

        packed_code_base_lines = self.packed_code_base.splitlines()
        last_import_line = max(lineno for lineno, line in enumerate(packed_code_base_lines)
                               if line.startswith("import ") or line.startswith("from "))
        future_code = '\n'.join(packed_code_base_lines[:last_import_line + 1])
        packed_code_base = '\n'.join(packed_code_base_lines[last_import_line + 2:])
        packed_code = future_code + "\n\n\n" + header + packed_code_base + footer

        return packed_code
