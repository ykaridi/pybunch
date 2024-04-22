import sys
from copy import deepcopy
from functools import reduce, cached_property
from pathlib import Path
from typing import Mapping, Dict, Tuple

_module_type = type(sys)


class DynamicLocalImporter:
    def __init__(self, codes: Mapping[str, str], clean_builtins: _module_type = None):
        self._codes = {Path(*pth.split('.')): code for pth, code in codes.items()}
        self._clean_builtins = clean_builtins if clean_builtins is not None else globals()['__builtins__']

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
                level: int = 0, overriden_name: str = None):
        if level == 0:
            return self._import_delegate(name, _globals, _locals, fromlist, level)
        else:
            current_dynamic_filepath = _globals['_dynamic_filepath']
            dynamic_filepath = (reduce(lambda p, _: p.parent, range(level), current_dynamic_filepath) /
                                Path(*name.split('.')))
            code = self._codes[dynamic_filepath]

            module = _module_type('.'.join(dynamic_filepath.parts) if overriden_name is None else overriden_name)
            module._dynamic_filepath = dynamic_filepath

            module.__builtins__ = self._adjusted_builtins
            exec(code, module.__dict__)
            return module

    def execute(self, module: str):
        _globals = {'_dynamic_filepath': Path('__main__')}
        self._import(module, _globals, None, (), 1, overriden_name='__main__')
