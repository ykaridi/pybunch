import importlib.resources
import ast
from functools import cached_property, reduce
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

    def translate_module(self, name: str) -> ModulePath:
        path = ModulePath.from_name(name)
        if self._package is not None and path.parts[0] != self._package:
            path = ModulePath(self._package) / path
        if path in self._package_mapping:
            return path
        return None

    def static_find_imports(self, entrypoint: ModulePath):
        visited = set()
        queue = {entrypoint}
        while queue:
            path = queue.pop()
            visited.add(path)

            tree = ast.parse(self._package_mapping[path].read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    level = node.level
                    if level == 0:
                        base = ModulePath()
                    else:
                        base = reduce(lambda p, _: p.parent, range(level), path)

                    base = base / ModulePath.from_name(node.module)
                    modules = [base]
                    for name in node.names:
                        modules.append(base / ModulePath.from_name(name.name))

                elif isinstance(node, ast.Import):
                    modules = [ModulePath.from_name(name.name) for name in node.names]
                else:
                    continue

                for module in modules:
                    if module in self._package_mapping:
                        if module not in visited and module not in queue:
                            queue.add(module)

                    while len(module.parts) > 0:
                        init = module / '__init__'
                        if init in self._package_mapping:
                            if init not in visited and module not in queue:
                                queue.add(init)
                        module = module.parent

        return visited

    def pack(self, entrypoint: str, statically_optimize: bool = False) -> str:
        entrypoint_path = self.translate_module(entrypoint)
        if entrypoint_path is None:
            raise ValueError("Nonexistent entrypoint")
        entrypoint = '.'.join(entrypoint_path.parts)

        included_packages = set(self._package_mapping.keys())
        if statically_optimize:
            included_packages = self.static_find_imports(entrypoint_path)

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
