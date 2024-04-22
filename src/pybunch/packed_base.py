import sys
from copy import deepcopy
from functools import reduce, cached_property
from pathlib import Path
from typing import Mapping, Dict, Tuple

_module_type = type(sys)


class DynamicLocalImporter:
    def __init__(self, codes: Mapping[str, str], clean_builtins: _module_type = None, sources_package: str = None):
        self._codes = {Path(*pth.split('.')): code for pth, code in codes.items()}
        self._base_modules = {pth.parts[0] for pth in self._codes}
        self._clean_builtins = clean_builtins if clean_builtins is not None else globals()['__builtins__']
        if sources_package:
            self._sources_package = Path(*sources_package.split('.'))
            self._base_modules.add(self._sources_package.parts[0])

    @cached_property
    def _builtins(self):
        if isinstance(self._clean_builtins, _module_type):
            return self._clean_builtins.__dict__
        elif isinstance(self._clean_builtins, dict):
            return self._clean_builtins
        else:
            raise ValueError('Unknown type for builtin module')

    @cached_property
    def _import_delegate(self):
        return self._builtins['__import__']

    @cached_property
    def _adjusted_builtins(self):
        builtins = deepcopy(self._builtins)
        builtins['__import__'] = self._import
        return builtins

    def _import(self, name: str, _globals: Dict = None, _locals: Dict = None, fromlist: Tuple[str, ...] = (),
                level: int = 0, name_override: str = None):
        path = Path(*name.split('.'))
        imports_base_module = path.parts[0] in self._base_modules
        imports_sources_package = False
        if self._sources_package:
            imports_sources_package = path.is_relative_to(self._sources_package)

        if level > 0 or (level == 0 and (imports_base_module or imports_sources_package)):
            base = Path()
            if level > 0:
                current_dynamic_filepath = _globals['_dynamic_filepath']
                base = reduce(lambda p, _: p.parent, range(level), current_dynamic_filepath)
            elif imports_sources_package:
                path = path.relative_to(self._sources_package)

            dynamic_filepath = base / path
            if dynamic_filepath not in self._codes:
                raise ModuleNotFoundError(f"Module '{name}' not found in pybunch bundled modules")

            code = self._codes[dynamic_filepath]

            module = _module_type('.'.join(dynamic_filepath.parts) if name_override is None else name_override)
            module._dynamic_filepath = dynamic_filepath

            module.__builtins__ = self._adjusted_builtins
            exec(code, module.__dict__)
            return module
        else:
            return self._import_delegate(name, _globals, _locals, fromlist, level)

    def execute(self, module: str):
        _globals = {'_dynamic_filepath': Path('__main__')}
        self._import(module, _globals, None, (), 1, name_override='__main__')
