# Standard Library
import abc
import inspect
from pathlib import Path
import sys
from typing import Any, Iterable, List, Type, Union

# Patterns
from patterns.state import settings
from patterns.state._structs import (
    StateAttribute,
    StateDefinition,
    StateItem,
    StateMember,
    StateMethod,
    StateMethodBase,
    StateProperty,
    StateTransition,
)
from patterns.state.exceptions import StateError

INDENT = ' ' * 4

unset = object()


def create_function(
    name: str,
    arguments: Union[str, Iterable[str]],
    body_lines: Iterable[str],
    return_type: Any = unset,
    globals_: dict = None,
):
    if isinstance(arguments, str):
        function_parameters_part = arguments
    else:
        function_parameters_part = f'({", ".join(arguments)})'
    function_body = '\n'.join(f'{INDENT}{line}' for line in body_lines)

    if return_type is not unset:
        return_type_part = f' -> _return_type'
        globals_['_return_type'] = return_type
    else:
        return_type_part = ''

    function_txt = (
        f'def {name}{function_parameters_part}{return_type_part}:\n{function_body}'
    )
    ns = {}
    exec(function_txt, globals_, ns)
    return ns[name]


def resolve_type(module: str, name: str):
    return sys.modules[module].__dict__[name]


def get_original_function_signature_str(function) -> str:
    return str(inspect.signature(function))


def get_wrapped_param_call(function) -> str:
    signature = inspect.signature(function)
    param_strings = []
    for param in signature.parameters.values():
        if param.name == 'self':
            continue
        elif param.kind == inspect.Parameter.POSITIONAL_ONLY:
            param_strings.append(param.name)
        elif param.kind == inspect.Parameter.VAR_POSITIONAL:
            param_strings.append(f'*{param.name}')
        elif param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD:
            param_strings.append(param.name)
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            param_strings.append(f'**{param.name}')
        elif param.kind == inspect.Parameter.KEYWORD_ONLY:
            param_strings.append(f'{param.name}={param.name}')
        else:
            raise ValueError(f'Unexpected kind of parameter: {param.kind}.')

    return ', '.join(param_strings)


def create_wrapped_state_init(cls: Type, initial_state: StateItem):
    if cls.__init__ is not object.__init__:
        arguments = get_original_function_signature_str(cls.__init__)
        globals_ = cls.__init__.__globals__
        wrapped_call_arguments = get_wrapped_param_call(function=cls.__init__)
    else:
        arguments = ['self', '*args', '**kwargs']
        globals_ = {}
        wrapped_call_arguments = 'self, *args, **kwargs'

    return create_function(
        name='__init__',
        arguments=arguments,
        globals_={
            'current_init': cls.__init__,
            'default_state_cls': initial_state.cls,
            **globals_,
        },
        body_lines=[
            f'current_init({wrapped_call_arguments})',
            'self._state = default_state_cls()',
        ],
    )


class StateMemberWrapperGenerator(abc.ABC):
    def __init__(self, member: StateMember):
        self.member = member

    def create_wrapper(self):
        return create_function(
            name=self.member.name,
            arguments=self._get_arguments(),
            body_lines=self._get_body_lines(),
            return_type=self._get_return_type(),
            globals_=self._get_globals(),
        )

    @abc.abstractmethod
    def _get_arguments(self) -> Union[str, List[str]]:
        ...

    def _get_globals(self) -> dict:
        return {'StateError': StateError}

    def _get_return_type(self) -> Any:
        return unset

    def _get_body_lines(self) -> List[str]:
        return [
            f'if "{self.member.name}" not in self._state.{settings.STATE_CLS_MEMBER_SET_KEY}:',
            f'{INDENT}err_msg = (',
            f'{INDENT}{INDENT}f"' + '{self.__class__.__name__} object in state "',
            f'{INDENT}{INDENT}f"'
            + '{self._state.__class__.__name__} does not support calling "',
            f'{INDENT}{INDENT}"{self.member.name}."',
            f'{INDENT})',
            f'{INDENT}raise StateError(err_msg)',
            *self._get_return_lines(),
        ]

    def _get_return_lines(self) -> List[str]:
        return [f'return self._state.{self.member.name}']


class StateAttributeWrapperGenerator(StateMemberWrapperGenerator):
    member: StateAttribute

    def _get_arguments(self) -> List[str]:
        return ['self']

    def _get_return_type(self):
        return self.member.type_


class StateMethodBaseWrapperGenerator(StateMemberWrapperGenerator):
    member: StateMethodBase

    def _get_arguments(self) -> str:
        return get_original_function_signature_str(self.member.function)

    def _get_return_type(self):
        return unset

    def _get_globals(self) -> dict:
        return {
            **super()._get_globals(),
            self.member.name: self.member.function,
            **self.member.function.__globals__,
        }


class StateMethodWrapperGenerator(StateMethodBaseWrapperGenerator):
    member: StateMethod

    def _get_return_lines(self) -> List[str]:
        wrapped_call_arguments = get_wrapped_param_call(function=self.member.function)
        return [f'return self._state.{self.member.name}({wrapped_call_arguments})']


class StatePropertyWrapperGenerator(StateMethodBaseWrapperGenerator):
    member: StateProperty

    def _get_arguments(self) -> List[str]:
        return ['self']


class StateTransitionWrapperGenerator(StateMethodBaseWrapperGenerator):
    member: StateTransition

    def _get_return_lines(self) -> List[str]:
        wrapped_call_arguments = get_wrapped_param_call(function=self.member.function)
        return [
            f'new_state = self._state.{self.member.name}({wrapped_call_arguments})',
            f'self._state = new_state',
            f'return None',
        ]


def composed_wrapper_generator_factory(
    member: StateMember,
) -> StateMemberWrapperGenerator:
    if type(member) is StateAttribute:
        return StateAttributeWrapperGenerator(member)
    elif type(member) is StateMethod:
        return StateMethodWrapperGenerator(member)
    elif type(member) is StateProperty:
        return StatePropertyWrapperGenerator(member)
    elif type(member) is StateTransition:
        return StateTransitionWrapperGenerator(member)
    else:
        raise NotImplementedError(f'Unhandled member type: {type(member)}.')


class StateMemberStubGenerator(abc.ABC):
    def __init__(self, member: StateMember):
        self.member = member

    @abc.abstractmethod
    def generate_stub_line(self) -> str:
        ...


class StateAttributeStubGenerator(StateMemberStubGenerator):
    member: StateAttribute

    def generate_stub_line(self) -> str:
        type_annotation_string = inspect.formatannotation(self.member.type_)
        return f'{self.member.name}: {type_annotation_string}'


class StateMethodStubGenerator(StateMemberStubGenerator):
    member: StateMethod

    def generate_stub_line(self) -> str:
        signature = inspect.signature(self.member.function)
        return f'def {self.member.name}{signature}: ...'


class StatePropertyStubGenerator(StateMemberStubGenerator):
    member: StateProperty

    def generate_stub_line(self) -> str:
        signature = inspect.signature(self.member.function)
        return f'def {self.member.name}{signature}: ...'


class StateTransitionStubGenerator(StateMemberStubGenerator):
    member: StateTransition

    def generate_stub_line(self) -> str:
        signature = inspect.signature(self.member.function)
        signature_string = str(signature)
        signature_string, _, _ = signature_string.partition(' ->')
        return f'def {self.member.name}{signature_string} -> None: ...'


def composed_stub_generator_factory(member: StateMember):
    if type(member) is StateAttribute:
        return StateAttributeStubGenerator(member)
    elif type(member) is StateMethod:
        return StateMethodStubGenerator(member)
    elif type(member) is StateProperty:
        return StatePropertyStubGenerator(member)
    elif type(member) is StateTransition:
        return StateTransitionStubGenerator(member)
    else:
        raise NotImplementedError(f'Unhandled member type: {type(member)}.')


# TODO(BK): for now this can handle being called only once (for our test-case okay)
# TODO(BK): if existent, stubs are the truth, so we need to add everything from class
#           that concerns functions and annotations (how to deal with __init__?)
class StubGenerator:
    def generate_for_cls(self, cls: Type, state_definition: StateDefinition) -> None:
        file_path = Path(sys.modules[cls.__module__].__file__)
        self._check_no_overwrite(file_path)

        # TODO(BK): resolve duplicates
        # TODO(BK): add imports for states (rspv. all other classes...)
        # TODO(BK): comment for state (available in state...)
        # TODO(BK): what about the other classes? Shall we add them? We cannot import
        #           them -> for this use-case not required, transition has None
        #           return-type
        imports_to_add = []
        cls_lines = [f'class {cls.__name__}:']
        # TODO(BK): ordered members isn't a good idea? -> gives us not enough control,
        #           and then it is superfluous anyway... -> get them here
        for member in state_definition.ordered_members():
            stub_generator = composed_stub_generator_factory(member)
            line = stub_generator.generate_stub_line()
            line = f'{INDENT}{line}'
            cls_lines.append(line)

        pyi_path = file_path.with_suffix('.pyi')
        with open(file=pyi_path, mode='w') as fp:
            fp.write('\n'.join(cls_lines))

    def _check_no_overwrite(self, path: Path):
        pyi_path = path.with_suffix('.pyi')
        if pyi_path.exists():
            raise FileExistsError(
                'pyi file {pyi_path} for already exist. Not yet smart enough to '
                'overwrite.'
            )
