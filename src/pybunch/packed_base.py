# This is for jython
from __future__ import division

import importlib
import itertools
import runpy
import sys
import os
import traceback
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
        self.file_name = 'pybunch <%s>' % name
        self.path = ModulePath(*name.split('.'))
        self.parent_name = '.'.join(self.path.parts[:-1])
        self.package = None  # type: str
        self.source_code = code
        self._compiled = None  # type: 'code'
        self._module = None  # type: _module_type | None

    @property
    def compiled(self):
        # type: () -> 'code'
        if self._compiled is None:
            self._compiled = compile(self.source_code, self.file_name, 'exec')
        return self._compiled

    def is_package(self, name):
        # type: (str) -> bool
        return self.path.parts[-1] == '__init__'

    def load_module(self, name):
        # type: (str) -> _module_type
        if self._module is None:
            if self.is_package(None):
                module = _module_type(self.parent_name)
                self.package = '.'.join(self.path.parts[:-2])
                self.name = self.parent_name
                module.__path__ = []
            else:
                module = _module_type(self.name)
                self.package = self.parent_name

            module.__package__ = self.package
            module.__file__ = self.file_name
            self.run_module(_globals=module.__dict__)
            self._module = module

        return sys.modules.setdefault(name, self._module)

    def run_module(self, _globals=None, name=None):
        # type: (dict[str, object], str) -> dict[str, object]
        if _globals is None:
            _globals = {}

        _globals.update(__name__=name if name is not None else self.name,
                        __file__=self.file_name,
                        __loader__=self,
                        __package__=self.parent_name)

        restore_name = '__name__' in _globals
        old_filename = _globals.get('__name__', None)
        if name is not None:
            _globals['__name__'] = name

        exec(self.compiled, _globals)
        if restore_name:
            _globals[''] = old_filename
        else:
            del _globals['__name__']

        return _globals

    def get_code(self, name):
        # type: (str) -> 'code'
        return self.compiled

    def get_source(self, *args, **kwargs):
        return self.source_code


RESOLVED_IMPORT_EXTERNAL = 'External'
RESOLVED_IMPORT_MISSING_LOCAL = 'Missing Local'
RESOLVED_IMPORT_LEAF_MODULE = 'Leaf Module'
RESOLVED_IMPORT_INTERMEDIATE_MODULE = 'Intermediate Module'


class DynamicLocalImporter(object):
    def __init__(self, module_descriptions):
        # type: (dict[str, ModuleDescription]) -> None
        self._module_descriptions = {ModulePath.from_name(name): description
                                     for name, description in module_descriptions.items()}

        self._module_specs = {}  # dict[str, _module_type]

    @property
    def loaded_modules(self):
        # type: () -> set[str]
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
        # type: () -> 'Generator[None, None, None]'
        old_meta_path = sys.meta_path
        sys.meta_path = [self] + sys.meta_path
        yield
        sys.meta_path = old_meta_path

    @property
    @contextmanager
    def with_custom_stacktrace(self):
        # type: () -> 'Generator[None, None, None]'
        old_except_hook = sys.excepthook
        print_exception = traceback.print_exception

        def except_hook(ex_type, ex, tb):
            print_exception(ex_type, ex, tb)

        sys.excepthook = except_hook
        yield
        sys.excepthook = old_except_hook

    def import_module(self, module):
        # type: (str) -> _module_type
        with self.add_to_meta_path, self.with_custom_stacktrace:
            return importlib.import_module(module)

    def execute_module(self, module):
        # type: (str) -> _module_type
        with self.add_to_meta_path, self.with_custom_stacktrace:
            try:
                new_globals = runpy.run_module(module, run_name='__main__')
            except ImportError:
                # Fallback for jython
                imported_module = importlib.import_module(module)
                new_globals = imported_module.__loader__.run_module(name='__main__')

        current_globals = globals()
        keys_to_delete = set(current_globals.keys()).difference(new_globals)
        current_globals.update(new_globals)
        for key in keys_to_delete:
            del current_globals[key]

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
        # type: (str, str) -> ModuleDescription
        module_aliases = {}
        resolution_type, module_path = self.attempt_resolve_local_import(name, self._module_descriptions.keys(),
                                                                         module_aliases)

        if resolution_type == RESOLVED_IMPORT_LEAF_MODULE:
            return self._module_descriptions[module_path]
        elif resolution_type == RESOLVED_IMPORT_INTERMEDIATE_MODULE:
            return self._module_descriptions[module_path / '__init__']
