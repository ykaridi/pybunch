import argparse
from pathlib import Path
from .packed_base import ModulePath
from .project import Project


if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='pybunch',
                                     description='Pack a python project into a single executable file')
    parser.add_argument('-r', '--root', type=Path, required=True, help='Project root')
    parser.add_argument('-e', '--entrypoint', required=True, type=str,
                        help='Entry point of python project, relative to the project root')
    parser.add_argument('-p', '--package', required=False, default=None, type=str,
                        help='Package for bundled sources, allowing to import them with absolute imports'
                             ' to that package')
    parser.add_argument('-so', '--statically-optimize', action='store_true',
                        help='Include only files that are statically imported from the entrypoint onwards')
    parser.add_argument('-o', '--output', required=False, type=Path, default=None,
                        help='Output path for packed file, default is to stdout.')

    args = parser.parse_args()
    root = args.root
    entrypoint = args.entrypoint
    package = args.package
    statically_optimize = args.statically_optimize
    out_file = args.output

    project = Project({ModulePath(*pth.relative_to(root).with_suffix('').parts): pth for pth in root.glob('**/*.py')},
                      package)
    packed = project.pack(entrypoint, statically_optimize=statically_optimize)
    if out_file is not None:
        out_file.write_text(packed)
    else:
        print(packed)
