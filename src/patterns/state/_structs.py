# Standard Library
from dataclasses import dataclass, field
import enum
import itertools
from types import MappingProxyType
from typing import Callable, List, Optional, Tuple, Type, TypeVar, Union

# Patterns
from patterns.state.exceptions import StateConfigError


class StateMember:
    """Create the wrappers for the the target class."""

    name: str

    def modify_wrapper(self, wrapper: Callable):
        # some classes are properties and need to init a property from the wrapper
        return wrapper


@dataclass(frozen=True)
class StateAttribute(StateMember):
    name: str
    type_: Type

    def modify_wrapper(self, wrapper: Callable):
        return property(wrapper)


RegistryKey = Tuple[str, str]


@dataclass(frozen=True)
class StateMethodBase(StateMember):
    function: Callable

    @property
    def name(self):
        return self.function.__name__

    @property
    def registry_key(self) -> RegistryKey:
        cls_name, _, function_name = self.function.__qualname__.partition('.')
        if not function_name:
            raise StateConfigError(f'Cannot register function {cls_name}.')
        return self.function.__module__, cls_name


@dataclass(frozen=True)
class StateMethod(StateMethodBase):
    pass


@dataclass(frozen=True)
class StateProperty(StateMethodBase):
    def modify_wrapper(self, wrapper: Callable):
        return property(wrapper)


StateType = TypeVar('StateType', bound='Type')


@dataclass(frozen=True)
class StateTransition(StateMethodBase):
    transitions_to: Union[str, StateType]


@dataclass(frozen=True)
class MemberStateItem:
    properties: dict[str, StateProperty] = field(default_factory=dict)
    methods: dict[str, StateMethod] = field(default_factory=dict)
    transitions: dict[str, StateTransition] = field(default_factory=dict)


@dataclass(frozen=True)
class ClassStateItem:
    cls: Type
    initial: bool
    abstract: bool
    attributes: Optional[List[StateAttribute]]


class InternalItemState(enum.Enum):
    matched = 0
    resolved = 1


@dataclass(frozen=True)
class StateItem:
    cls: Type
    initial: bool
    abstract: bool
    attributes: MappingProxyType[str, StateAttribute]
    properties: MappingProxyType[str, StateProperty]
    methods: MappingProxyType[str, StateMethod]
    transitions: MappingProxyType[str, StateTransition]
    internal_state: InternalItemState

    @property
    def members(self) -> List[StateMember]:
        return [
            *self.attributes.values(),
            *self.properties.values(),
            *self.methods.values(),
            *self.transitions.values(),
        ]

    def inherit_from_state(self, other: 'StateItem') -> 'StateItem':
        return StateItem(
            cls=self.cls,
            initial=self.initial,
            abstract=self.abstract,
            attributes=MappingProxyType(
                mapping={**other.attributes, **self.attributes}
            ),
            methods=MappingProxyType(mapping={**other.methods, **self.methods}),
            properties=MappingProxyType(
                mapping={**other.properties, **self.properties}
            ),
            transitions=MappingProxyType(
                mapping={**other.transitions, **self.transitions}
            ),
            internal_state=InternalItemState.resolved,
        )

    def with_new_internal_state(self, state: InternalItemState):
        return StateItem(
            cls=self.cls,
            initial=self.initial,
            abstract=self.abstract,
            attributes=self.attributes,
            methods=self.methods,
            properties=self.properties,
            transitions=self.transitions,
            internal_state=state,
        )


@dataclass(frozen=True)
class StateDefinition:
    initial: StateItem
    concretes: Tuple[StateItem, ...]

    def ordered_members(self) -> List[StateMember]:
        return sorted(
            itertools.chain.from_iterable(state.members for state in self.concretes),
            key=lambda member: {
                StateAttribute: 0,
                StateProperty: 1,
                StateMethod: 2,
                StateTransition: 3,
            }[type(member)],
        )
