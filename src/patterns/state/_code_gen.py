# Standard Library
import abc
import inspect
import sys
from typing import Any, Iterable, List, Type, Union

# Patterns
from patterns.state._structs import (
    StateAttribute,
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
        if not function_parameters_part.startswith('('):
            function_parameters_part = f'({function_parameters_part}'
        if not function_parameters_part.endswith(')'):
            function_parameters_part = f'({function_parameters_part}'
    else:
        function_parameters_part = f'({", ".join(arguments)})'
    function_body = '\n'.join(f'{INDENT}{line}' for line in body_lines)
    return_type_part = f' -> _return_type' if return_type is not unset else ''
    globals_['_return_type'] = return_type
    function_txt = (
        f'def {name}{function_parameters_part}{return_type_part}:\n{function_body}'
    )
    ns = {}
    exec(function_txt, globals_, ns)
    return ns[name]


def resolve_type(module: str, name: str):
    return sys.modules[module].__dict__[name]


def get_original_function_signature_str(function) -> str:
    return str(inspect.Signature(function)).strip('(').strip(')')


def create_wrapped_state_init(cls: Type, initial_state: StateItem):
    if cls.__init__ is not object.__init__:
        arguments = get_original_function_signature_str(cls.__init__)
        globals_ = cls.__init__.__globals__
    else:
        arguments = ['self', '*args', '**kwargs']
        globals_ = {}

    return create_function(
        name='__init__',
        arguments=arguments,
        globals_={
            'current_init': cls.__init__,
            'default_state_cls': initial_state.cls,
            **globals_,
        },
        body_lines=[
            'current_init(self, *args, **kwargs)',
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
        body_lines = [
            'try:',
            self._get_original_call_line(),
            'except AttributeError as exc:',
            f'{INDENT}err_msg = (',
            f'{INDENT}{INDENT}f"' + '{self.__class__.__name__} object in state "',
            f'{INDENT}{INDENT}f"'
            + '{self._state.__class__.__name__} does not support calling "',
            f'{INDENT}{INDENT}"{self.member.name}."',
            f'{INDENT})',
            f'{INDENT}raise StateError(err_msg)',
        ]

        else_lines = self._get_else_lines()
        if else_lines:
            body_lines.extend(
                [
                    'else:',
                    *else_lines,
                ]
            )
        return body_lines

    @abc.abstractmethod
    def _get_original_call_line(self) -> str:
        ...

    @abc.abstractmethod
    def _get_else_lines(self) -> List[str]:
        ...


class StateAttributeWrapperGenerator(StateMemberWrapperGenerator):
    member: StateAttribute

    def _get_arguments(self) -> List[str]:
        return ['self']

    def _get_original_call_line(self) -> str:
        # TODO(BK): differentiate getting the method from the call (otherwise we might
        #           swallow unwanted AttributeErrors) -> does it apply here?
        return f'{INDENT}return self._state.{self.member.name}'

    def _get_return_type(self):
        # TODO(BK): does not work that way...
        return self.member.type_

    def _get_else_lines(self) -> List[str]:
        return []


class StateMethodBaseWrapperGenerator(StateMemberWrapperGenerator):
    member: StateMethodBase

    def _get_arguments(self) -> str:
        return get_original_function_signature_str(self.member.function)

    def _get_return_type(self):
        return self.member.function.__annotations__.get('return', unset)

    def _get_globals(self) -> dict:
        return {
            **super()._get_globals(),
            self.member.name: self.member.function,
            **self.member.function.__globals__,
        }


class StateMethodWrapperGenerator(StateMemberWrapperGenerator):
    member: StateMethod

    def _get_arguments(self) -> List[str]:
        # TODO(BK): original args?
        return ['self', '*args', '**kwargs']

    def _get_original_call_line(self) -> str:
        # TODO(BK): differentiate getting the method from the call (otherwise we might
        #           swallow unwanted AttributeErrors)
        return f'{INDENT}return self._state.{self.member.name}(*args, **kwargs)'

    def _get_else_lines(self) -> List[str]:
        return []


class StatePropertyWrapperGenerator(StateMemberWrapperGenerator):
    member: StateProperty

    def _get_arguments(self) -> List[str]:
        return ['self']

    def _get_original_call_line(self) -> str:
        # TODO(BK): differentiate getting the method from the call (otherwise we might
        #           swallow unwanted AttributeErrors)
        return f'{INDENT}return self._state.{self.member.name}'

    def _get_else_lines(self) -> List[str]:
        return []


class StateTransitionWrapperGenerator(StateMemberWrapperGenerator):
    member: StateTransition

    # TODO(BK): true signature?!
    def _get_arguments(self) -> List[str]:
        return ['self', '*args', '**kwargs']

    def _get_original_call_line(self) -> str:
        # TODO(BK): differentiate getting the method from the call (otherwise we might
        #           swallow unwanted AttributeErrors)
        return f'{INDENT}new_state = self._state.{self.member.name}(*args, **kwargs)'

    def _get_else_lines(self) -> List[str]:
        return [
            f'{INDENT}self._state = new_state',
            f'{INDENT}return None',
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
        # TODO(BK): type does not work like that
        return f'{INDENT}{self.member.name}: {self.member.type_}'


class StateMethodStubGenerator(StateMemberStubGenerator):
    member: StateMethod

    def generate_stub_line(self) -> str:
        return ''


class StatePropertyStubGenerator(StateMemberStubGenerator):
    member: StateProperty

    def generate_stub_line(self) -> str:
        return ''


class StateTransitionStubGenerator(StateMemberStubGenerator):
    member: StateTransition

    def generate_stub_line(self) -> str:
        return ''


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
