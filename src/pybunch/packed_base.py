import itertools
import sys
from copy import deepcopy
from enum import Enum
from functools import reduce, cached_property
from pathlib import Path
from typing import Mapping, Dict, Tuple, Iterable, Optional, Set

_module_type = type(sys)


class ResolvedImportType(Enum):
    EXTERNAL = 'External'
    MISSING_LOCAL = 'Missing Local'
    LEAF_MODULE = 'Leaf Module'
    INTERMEDIATE_MODULE = 'Intermediate Module'


class DynamicLocalImporter:
    def __init__(self, codes: Mapping[str, str], clean_builtins: _module_type = None, sources_package: str = None):
        self._codes = {Path(*pth.split('.')): code for pth, code in codes.items()}

        self._clean_builtins = clean_builtins if clean_builtins is not None else globals()['__builtins__']
        if sources_package:
            self._sources_package = Path(*sources_package.split('.'))

        self._modules: Dict[Path, _module_type] = {}
        self._locked_modules: Set[Path] = set()

    @property
    def modules(self):
        return self._modules

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

    @staticmethod
    def attempt_resolve_local_import(name: str, level: int, context: Path, local_modules: Iterable[Path],
                                     module_aliases: Dict[Path, Path] = None) \
            -> Tuple[ResolvedImportType, Optional[Path]]:
        local_modules = set(local_modules)
        if module_aliases is None:
            module_aliases = {}

        if not all(a == b or not a.is_relative_to(b) for a, b in itertools.product(module_aliases.keys(), repeat=2)):
            raise ValueError("Module aliases must be distinct")

        path = Path(*name.split('.'))
        imports_base_module = path.parts[0] in {local_module.parts[0] for local_module in local_modules}
        base_alias = next((base for base in module_aliases.keys() if path.is_relative_to(base)), None)

        if level > 0 or (level == 0 and (imports_base_module or base_alias is not None)):
            base = Path()
            if level > 0:
                base = reduce(lambda p, _: p.parent, range(level), context)
            elif base_alias is not None:
                path = module_aliases[base_alias] / path.relative_to(base_alias)

            imported_module = base / path
            if imported_module in local_modules:
                return ResolvedImportType.LEAF_MODULE, imported_module

            if (imported_module / '__init__') in local_modules:
                return ResolvedImportType.INTERMEDIATE_MODULE, imported_module

            return ResolvedImportType.MISSING_LOCAL, None
        else:
            return ResolvedImportType.EXTERNAL, None

    def _lock_module(self, path: Path):
        if path in self._locked_modules:
            raise ImportError("pybunch has encountered a cyclic import")
        self._locked_modules.add(path)

    def _import_leaf_module(self, path: Path, name: str = None):
        if path in self._modules:
            return self._modules[path]

        self._lock_module(path)

        code = self._codes[path]
        module = _module_type('.'.join(path.parts) if name is None else name)
        module._pybunch_context = path

        module.__builtins__ = self._adjusted_builtins
        exec(code, module.__dict__)

        self._modules[path] = module
        return module

    def _import_intermediate_module(self, path: Path):
        if path in self._modules:
            return self._modules[path]

        self._lock_module(path)

        module = _module_type('.'.join(path.parts))
        module._pybunch_context = path

        for submodule in self._codes:
            if not submodule.is_relative_to(path):
                continue

            relative_path = submodule.relative_to(path)
            distance = len(relative_path.parts)
            if relative_path.name == '__init__':
                # Intermediate Module
                if distance == 2:
                    module.__dict__[relative_path.parent.name] = self._import_intermediate_module(submodule)
            else:
                # Leaf module
                if distance == 1:
                    module.__dict__[relative_path.name] = self._import_leaf_module(submodule)

        code = self._codes[path / '__init__']
        module.__builtins__ = self._adjusted_builtins
        exec(code, module.__dict__)

        self._modules[path] = module
        return module

    def _import(self, name: str, _globals: Dict = None, _locals: Dict = None, fromlist: Tuple[str, ...] = (),
                level: int = 0, name_override: str = None):
        module_aliases = {}
        if self._sources_package is not None:
            module_aliases[self._sources_package] = Path()

        resolution_type, module_path = self.attempt_resolve_local_import(name, level, _globals['_pybunch_context'],
                                                                         self._codes.keys(), module_aliases)

        if resolution_type is ResolvedImportType.EXTERNAL:
            return self._import_delegate(name, _globals, _locals, fromlist, level)
        elif resolution_type is ResolvedImportType.MISSING_LOCAL:
            raise ModuleNotFoundError(f"Module '{name}' not found in pybunch bundled modules")
        else:
            if resolution_type is ResolvedImportType.INTERMEDIATE_MODULE:
                return self._import_intermediate_module(module_path)
            elif resolution_type is ResolvedImportType.LEAF_MODULE:
                return self._import_leaf_module(module_path, name=name_override)

            return self._modules[module_path]

    def import_module(self, module: str):
        _globals = {'_pybunch_context': Path('__main__')}
        return self._import(module, _globals, None, (), 1)

    def execute_module(self, module: str):
        _globals = {'_pybunch_context': Path('__main__')}
        self._import(module, _globals, None, (), 1, name_override='__main__')
