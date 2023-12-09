# Standard Library
import os
from pathlib import Path
import sys
from typing import List, Tuple, Type

# Third Party
import click

# Patterns
from patterns.state._add import AddState
from patterns.state._code_gen import composed_stub_generator_factory
from patterns.state._structs import StateDefinition

# TODO(BK): document that PYTHONPATH must be given somehow? -> code in the module must
#           be executed; maybe define custom loader?
BASE_PATH = Path(os.environ['PYTHONPATH']).absolute()

# TODO(BK): if existent, stubs are the truth, so we need to add everything from class
#           that concerns functions and annotations (how to deal with __init__?)


def generate_stubs(path, overwrite):
    path = Path(path)
    if path.is_file():
        paths = [path]
    elif path.is_dir():
        paths = path.rglob('*.py')
    else:
        raise NotImplementedError('Unhandled case. Should not happen.')

    existing_pyi_paths = []
    if not overwrite:
        for path in paths:
            pyi_path = path.with_suffix('.pyi')
            if pyi_path.exists():
                existing_pyi_paths.append(path)

        path_list = '\n'.join(str(p) for p in existing_pyi_paths)
        raise FileExistsError(
            f'pyi file for following paths already exist. Use --overwrite to overwrite '
            f'them: \n{path_list}'
        )

    # TODO(BK): relative to module, but also we need to import stuff
    def module_name_from_path(path: Path):
        ...

    # breakpoint()
    p = Path.home() / 'devel/patterns/tests'
    assert p.exists()
    sys.path.append(str(p))
    sys.path.append(str(p / 'state_pattern'))
    # TODO(BK): if patterns package is installed, it would just work without the need to set
    #           python-path to src
    # make sure code ran for all modules via importing them
    # Standard Library
    import importlib

    for path in paths:
        module_name = module_name_from_path(path)
        importlib.import_module(module_name)

    for path in paths:
        generate_stubs_for_file(path)


def generate_stubs_for_file(path: Path):
    if not path.is_file():
        raise FileNotFoundError(f'{path} is not a file.')

    pyi_path = path.with_suffix('.pyi')
    lines = generate_lines_for_stub_file(path)
    with open(file=pyi_path, mode='w') as fp:
        fp.write('\n'.join(lines))


def generate_lines_for_stub_file(path: Path) -> List[str]:
    all_cls_lines = []
    all_imports_to_add = []
    for cls, state_definition in AddState.cls_to_state().items():
        if cls.__file__ == str(path):
            imports_to_add, cls_lines = generate_stub_lines_for_cls(
                cls, state_definition
            )
            all_imports_to_add.extend(imports_to_add)
            all_cls_lines.extend(cls_lines)
            all_cls_lines.extend(['\n', '\n'])

    # TODO(BK): order imports? -> can we use isort programmatically? -> or should they
    #           be linted manually?
    return [
        *all_imports_to_add,
        '\n',
        '\n',
        *all_cls_lines,
    ]


def generate_stub_lines_for_cls(
    cls: Type, state_definition: StateDefinition
) -> Tuple[List[str], List[str]]:
    # TODO(BK): resolve duplicates
    # TODO(BK): add imports for states (rspv. all other classes...)
    # TODO(BK): comment for state (available in state...)
    imports_to_add = []
    cls_lines = [f'class {cls.__name__}:']
    for member in state_definition.ordered_members():
        stub_generator = composed_stub_generator_factory(member)
        cls_lines.append(stub_generator.generate_stub_line())

    return imports_to_add, cls_lines


@click.command('generate_stubs')
@click.option(
    '--path', required=True, type=click.Path(file_okay=True, dir_okay=True, exists=True)
)
@click.option('--overwrite', required=False, is_flag=True, type=bool, default=False)
def run(*args, **kwargs):
    """
    Stubs are the truth for type-checkers, so we only put the members there that are
    added by the state-pattern code to the classes.
    """
    generate_stubs(*args, **kwargs)


if __name__ == '__main__':
    run()
