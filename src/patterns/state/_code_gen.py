# Standard Library
import abc
import inspect
import itertools
from pathlib import Path
import sys
from typing import Any, Iterable, List, Optional, Type, Union

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


def generate_stubs(cls: Type, state_definition: StateDefinition) -> None:
    file_path = Path(sys.modules[cls.__module__].__file__)
    pyi_path = file_path.with_suffix('.pyi')

    if not pyi_path.exists():
        stub_file = StubFile(objects=[])
    else:
        stub_file = StubFile.deserialize_from_path(path=pyi_path)

    stub_file.add_cls(cls, state_definition)
    stub_file.serialize_to_path(path=pyi_path)


class StubObject(abc.ABC):
    empty_lines_after: int

    def __init__(self, empty_lines_after: Optional[int] = None):
        self.empty_lines_after = empty_lines_after or self.empty_lines_after

    @abc.abstractmethod
    def serialize(self) -> List[str]:
        return ['\n'] * self.empty_lines_after

    @classmethod
    @abc.abstractmethod
    def deserialize(cls, lines: Iterable[str]) -> "StubObject":
        ...


class StubFile(StubObject):
    empty_lines_after = 1

    def __init__(
        self, objects: List[StubObject], empty_lines_after: Optional[int] = None
    ):
        super().__init__(empty_lines_after)
        # TODO(BK): or rather a map? -> rather separated class-map
        self._objects: List[StubObject] = objects

    @classmethod
    def deserialize_from_path(cls, path: Path) -> "StubFile":
        with open(str(path), mode='r') as fp:
            return cls.deserialize(lines=fp.readlines())

    def serialize_to_path(self, path: Path) -> None:
        with open(str(path), mode='w') as fp:
            lines = self.serialize()
            fp.write('\n'.join(lines))

    @classmethod
    def deserialize(cls, lines: Iterable[str]) -> "StubFile":
        # TODO(BK): do the following: implement a StubFile class that will get the stub-files's
        #           lines and analyses them into sections, such that we can give members and
        #           then parse everything back
        objects = []
        lines_iter = iter(lines)
        while True:
            try:
                line = next(lines_iter)
            except StopIteration:
                break

            for stub_cls in []:
                if stub_cls.match(line):
                    break

            if line.strip() == '':
                objects.append(UnspecificStubLine.deserialize([line]))
                objects[-2].empty_lines_after += 1

        return StubFile(objects)

    def serialize(self) -> List[str]:
        return list(
            itertools.chain.from_iterable(obj.serialize() for obj in self._objects)
        )

    def add_cls(self, cls: Type, state_definition: StateDefinition) -> None:
        # TODO(BK): if existent, stubs are the truth, so we need to add everything from class
        #           that concerns functions and annotations (how to deal with __init__?)
        # TODO(BK): read stuff from cls
        # TODO(BK): read members
        ...


class StubGenerator:
    def generate_for_cls(self, cls: Type, state_definition: StateDefinition) -> None:
        # TODO(BK): resolve duplicates
        # TODO(BK): add imports for states (rspv. all other classes...)
        # TODO(BK): comment for state (available in state...)
        # TODO(BK): what about the other classes? Shall we add them? We cannot import
        #           them -> for this use-case not required, transition has None
        #           return-type -> just check if they are imported and if so, make them
        #           a string or so for now
        imports_to_add = []
        cls_lines = [f'class {cls.__name__}:']
        # TODO(BK): ordered members isn't a good idea? -> gives us not enough control,
        #           and then it is superfluous anyway... -> get them here
        for member in state_definition.ordered_members():
            stub_generator = composed_stub_generator_factory(member)
            line = stub_generator.generate_stub_line()
            line = f'{INDENT}{line}'
            cls_lines.append(line)


class StubClass(StubObject):
    empty_lines_after = 2


class StubMethod(StubObject):
    empty_lines_after = 0


class StubAttribute(StubObject):
    empty_lines_after = 0


class UnspecificStubLine(StubObject):
    empty_lines_after = 0
