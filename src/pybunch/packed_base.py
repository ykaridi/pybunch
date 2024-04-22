# This is for jython
from __future__ import division

import importlib
import itertools
import runpy
import sys
import os
from contextlib import contextmanager

_module_type = type(os)


class ModulePath(object):
    def __init__(self, *parts):
        # type: (*str) -> None
        self.parts = tuple(parts)

    @staticmethod
    def from_name(name):
        # type: (str) -> 'ModulePath'
        return ModulePath(*name.split('.'))

    @property
    def name(self):
        # type: () -> str
        return self.parts[-1]

    @property
    def parent(self):
        # type: () -> 'ModulePath'
        return ModulePath(*self.parts[:-1])

    def __truediv__(self, other):
        # type: ('ModulePath' | str) -> 'ModulePath'
        if isinstance(other, ModulePath):
            return ModulePath(*(self.parts + other.parts))
        elif isinstance(other, str):
            return ModulePath(*(self.parts + (other, )))
        else:
            raise ValueError("Can only concat ModulePath with str or ModulePath")

    def is_relative_to(self, other):
        # type: ('ModulePath') -> bool
        length = len(other.parts)
        return length <= len(self.parts) and self.parts[:length] == other.parts

    def relative_to(self, other):
        # type: ('ModulePath') -> 'ModulePath'
        if not self.is_relative_to(other):
            raise ValueError("ModulePath must be relative to given ModulePath")

        return ModulePath(*self.parts[len(other.parts):])

    def __hash__(self):
        # type: () -> int
        return hash(self.parts)

    def __eq__(self, other):
        # type: (object) -> bool
        if not isinstance(other, ModulePath):
            return False
        return self.parts == other.parts

    def __str__(self):
        # type: () -> str
        return '.'.join(self.parts)

    def __repr__(self):
        # type: () -> str
        return 'ModulePath%s' % repr(self.parts)


class ModuleDescription(object):
    def __init__(self, name, code):
        # type: (str, str) -> None
        self.name = name
        self.path = ModulePath(*name.split('.'))
        self.code = code
        self._module = None  # type: _module_type | None

    def is_package(self, name):
        return self.path.parts[-1] == '__init__'

    def load_module(self, name):
        if self._module is None:
            parent = '.'.join(self.path.parts[:-1])
            if self.is_package(None):
                module = _module_type(parent)
                module.__path__ = []
            else:
                module = _module_type(self.name)

            module.__package__ = parent
            module.__file__ = "pybunch <%s>" % self.name
            module.__loader__ = self
            exec(self.code, module.__dict__)
            self._module = module

        return sys.modules.setdefault(name, self._module)

    def get_code(self, name):
        return self.code


RESOLVED_IMPORT_EXTERNAL = 'External'
RESOLVED_IMPORT_MISSING_LOCAL = 'Missing Local'
RESOLVED_IMPORT_LEAF_MODULE = 'Leaf Module'
RESOLVED_IMPORT_INTERMEDIATE_MODULE = 'Intermediate Module'


class DynamicLocalImporter:
    def __init__(self, module_descriptions):
        # type: (dict[str, ModuleDescription], _module_type) -> None
        self._module_descriptions = {ModulePath.from_name(name): description
                                     for name, description in module_descriptions.items()}

        self._module_specs = {}  # dict[ModulePath, _module_type]

    @property
    def loaded_modules(self):
        return set(self._module_specs.keys())

    @staticmethod
    def attempt_resolve_local_import(name, local_modules, module_aliases=None):
        # type: (str, list[ModulePath], dict[ModulePath, ModulePath]) -> tuple[str, ModulePath | None]
        local_modules = set(local_modules)
        if module_aliases is None:
            module_aliases = {}

        if not all(a == b or not a.is_relative_to(b) for a, b in itertools.product(module_aliases.keys(), repeat=2)):
            raise ValueError("Module aliases must be distinct")

        path = ModulePath.from_name(name)
        imports_base_module = path.parts[0] in {local_module.parts[0] for local_module in local_modules}
        base_alias = next((base for base in module_aliases.keys() if path.is_relative_to(base)), None)

        if imports_base_module or base_alias is not None:
            base = ModulePath()
            if base_alias is not None:
                path = module_aliases[base_alias] / path.relative_to(base_alias)

            imported_module = base / path
            if imported_module in local_modules:
                return RESOLVED_IMPORT_LEAF_MODULE, imported_module

            if (imported_module / '__init__') in local_modules:
                return RESOLVED_IMPORT_INTERMEDIATE_MODULE, imported_module

            return RESOLVED_IMPORT_MISSING_LOCAL, None
        else:
            return RESOLVED_IMPORT_EXTERNAL, None

    @property
    @contextmanager
    def add_to_meta_path(self):
        old_meta_path = sys.meta_path
        sys.meta_path = [self] + sys.meta_path
        yield
        sys.meta_path = old_meta_path

    def import_module(self, module):
        # type: (str) -> _module_type
        with self.add_to_meta_path:
            importlib.import_module(module)

    def execute_module(self, module):
        # type: (str) -> _module_type
        with self.add_to_meta_path:
            runpy.run_module(module, run_name='__main__')

    def find_spec(self, name, path, target=None):
        # type: (str, str, object) -> 'ModuleSpec'
        from importlib.util import spec_from_loader

        if name not in self._module_specs:
            module_aliases = {}
            resolution_type, module_path = self.attempt_resolve_local_import(name,
                                                                             self._module_descriptions.keys(),
                                                                             module_aliases)

            if resolution_type == RESOLVED_IMPORT_LEAF_MODULE:
                self._module_specs[name] = spec_from_loader(name, self._module_descriptions[module_path])
            elif resolution_type == RESOLVED_IMPORT_INTERMEDIATE_MODULE:
                self._module_specs[name] = spec_from_loader(name, self._module_descriptions[module_path / '__init__'],
                                                            is_package=True)

        module_spec = self._module_specs.get(name, None)
        if module_spec is not None:
            return module_spec

    def find_module(self, name, path=None):
        module_aliases = {}
        resolution_type, module_path = self.attempt_resolve_local_import(name, self._module_descriptions.keys(),
                                                                         module_aliases)

        if resolution_type == RESOLVED_IMPORT_LEAF_MODULE:
            return self._module_descriptions[module_path]
        elif resolution_type == RESOLVED_IMPORT_INTERMEDIATE_MODULE:
            return self._module_descriptions[module_path / '__init__']
